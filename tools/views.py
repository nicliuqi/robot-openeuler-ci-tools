import logging
import subprocess
from django.http import JsonResponse
from multiprocessing import Process
from rest_framework.generics import GenericAPIView
from tools.permissions import ReviewPermission
from advisors import gitee
from advisors.review_tool import find_review_comment


logger = logging.getLogger('log')


def review(url):
    logger.info('Starting to review Pull Request')
    subprocess.call('python3 advisors/review_tool.py -u {} -c -l'.format(url), shell=True)


def edit_review(url, content):
    logger.info('Starting to edit review status')
    subprocess.call('python3 advisors/review_tool.py -u {} -e {} -l'.format(url, content), shell=True)


def base_log(pr_url, hook_name, action):
    logger.info('URL of Pull Request: {}'.format(pr_url))
    logger.info('Hook Name: {}'.format(hook_name))
    logger.info('Action: {}'.format(action))


class ReviewView(GenericAPIView):
    permission_classes = (ReviewPermission,)

    def post(self, request, *args, **kwargs):
        data = self.request.data
        try:
            hook_name = data['hook_name']
            action = data['action']
            pr_url = data['pull_request']['html_url']
        except (KeyError, TypeError):
            res = JsonResponse({'code': 400, 'msg': 'Bac Request'})
            res.status_code = 400
            return res

        if hook_name == 'merge_request_hooks' and action == 'open':
            base_log(pr_url, hook_name, action)
            logger.info('Notice Pull Request created')
            p1 = Process(target=review, args=(pr_url,))
            p1.start()
        elif hook_name == 'merge_request_hooks' and action == 'update':
            logger.info('Notice Pull Request update')
            try:
                action_desc = data['action_desc']
                logger.info('Action Description: {}'.format(action_desc))
                if action_desc == 'source_branch_changed':
                    base_log(pr_url, hook_name, action)
                    p2 = Process(target=review, args=(pr_url,))
                    p2.start()
                else:
                    logger.info('Notice no source branch changed, skip...')
            except KeyError:
                logger.info('Invaild update request, skip...')
        elif hook_name == 'note_hooks' and action == 'comment':
            base_log(pr_url, hook_name, action)
            logger.info('Notice Pull Request comment')
            comment = data['comment']['body']
            logger.info('Comment Body: {}'.format(comment))
            user_gitee = gitee.Gitee()
            owner, repo, number = pr_url.split('/')[3], pr_url.split('/')[4], pr_url.split('/')[6]
            latest_review_comment = find_review_comment(user_gitee, owner, repo, number)
            items = latest_review_comment['body'].splitlines()
            if '/lgtm' in comment.split('\n'):
                latest_review_comment_id = latest_review_comment['id']
                commenter = data['comment']['user']['login']
                edit_nums = []
                pr_lgtm_lst = get_pr_lgtm_lst(user_gitee, owner, repo, number, latest_review_comment_id)
                for item in items:
                    if ('@' + commenter) in item:
                        if '移交' in item:
                            period = item.split('|')[4].split('需要')[1].split('各有至少一名')[0]
                            owners1 = [x[1:] for x in period.split('及')[0].split('的 ')[1].split(' ')[:-1]]
                            owners2 = [x[1:] for x in period.split('及')[1].split('的 ')[1].split(' ')[:-1]]
                            owners1_agreement = False
                            owners2_agreement = False
                            for owner1 in owners1:
                                if owner1 in pr_lgtm_lst:
                                    owners1_agreement = True
                            for owner2 in owners2:
                                if owner2 not in owners1 and owner2 in pr_lgtm_lst:
                                    owners2_agreement = True
                            if owners1_agreement and owners2_agreement:
                                edit_nums.append(item.split('|')[1])
                        elif 'each SIG' in item:
                            owners1 = [x[1:] for x in item.split('|')[4].split('one of')[1].split('of')[0].split(' ')[1:-1]]
                            owners2 = [x[1:] for x in item.split('|')[4].split('one of')[2].split('of **')[0].split(' ')[1:-1]]
                            owners1_agreement = False
                            owners2_agreement = False
                            for owner1 in owners1:
                                if owner1 in pr_lgtm_lst:
                                    owners1_agreement = True
                            for owner2 in owners2:
                                if owner2 not in owners1 and owner2 in pr_lgtm_lst:
                                    owners2_agreement = True
                            if owners1_agreement and owners2_agreement:
                                edit_nums.append(item.split('|')[1])
                        elif '至少两人' in item:
                            owners =[x[1:] for x in item.split('需要')[1].split('中至少两人')[0].split(' ')[1:-1]]
                            count = 0
                            for owner in owners:
                                if owner in pr_lgtm_lst:
                                    count += 1
                            if count >= 2:
                                edit_nums.append(item.split('|')[1])
                        elif 'At least two of' in item:
                            owners = [x[1:] for x in item.split('At least two of')[1].split('must leave')[0].split(' ')[1:-1]]
                            count = 0
                            for owner in owners:
                                if owner in pr_lgtm_lst:
                                    count += 1
                            if count >= 2:
                                edit_nums.append(item.split('|')[1])
                        else:
                            edit_nums.append(item.split('|')[1])
                if edit_nums:
                    logger.info('The following item will be changed to be status "go": {}'.format(','.join(edit_nums)))
                    edit_string = 'go:' + ','.join(edit_nums)
                    p5 = Process(target=edit_review, args=(pr_url, edit_string))
                    p5.start()
            elif comment.startswith('/review '):
                lines = comment.splitlines()
                try:
                    if len(lines) == 1 and lines[0].strip().split(maxsplit=1)[1] == "retrigger":
                        p3 = Process(target=review, args=(pr_url,))
                        p3.start()
                    else:
                        lgtm_items = get_lgtm_items(user_gitee, owner, repo, number)
                        sets_li = []
                        for line in lines:
                            if line.strip().startswith("/review "):
                                sets = line.strip().split(maxsplit=1)[1]
                                sets = filter_review(sets, lgtm_items, len(items))
                                sets_li.append(sets)
                        contents = " ".join(sets_li)
                        if contents:
                            logger.info(contents)
                            p4 = Process(target=edit_review, args=(pr_url, contents))
                            p4.start()
                except IndexError:
                    pass
        return JsonResponse({'code': 200, 'msg': 'OK'})


def get_pr_lgtm_lst(user_gitee, owner, repo, number, review_id):
    pr_lgtm_lst = []
    all_comments = user_gitee.get_pr_comments_all(owner, repo, number)
    for comment in all_comments:
        if comment['id'] > review_id and '/lgtm' in comment['body'].split('\n'):
            pr_lgtm_lst.append(comment['user']['login'])
    return pr_lgtm_lst


def get_lgtm_items(user_gitee, owner, repo, number):
    latest_review_comment = find_review_comment(user_gitee, owner, repo, number)
    items = latest_review_comment['body'].splitlines()
    lgtm_items_numbers = []
    for item in items:
        if '/lgtm' in item:
            lgtm_items_numbers.append(item.split('|')[1])
    return lgtm_items_numbers


def filter_review(edit_str, lgtm_items, review_items_length):
    edit_dict = {}
    for i in edit_str.split():
        k, v = i.split(':')
        nums = []
        if v == '999':
            for j in range(review_items_length):
                if str(j) not in lgtm_items:
                    nums.append(str(j))
        elif '-' in v:
            left, right = v.split('-')
            for j in range(int(left), int(right) + 1):
                if str(j) not in lgtm_items:
                    nums.append(str(j))
        else:
            tmp_nums = v.split(',')
            for j in tmp_nums:
                if j not in lgtm_items:
                    nums.append(j)
        edit_dict[k] = nums
    contents = []
    for i in edit_dict:
        contents.append(i + ':' + ','.join(edit_dict[i]))
    return ' '.join(contents)
