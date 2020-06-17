import argparse
import json
import re
from datetime import datetime

import requests

DATE_MASK = "%Y-%m-%dT%H:%M:%SZ"
DEFAULT_BRANCH = "master"
DEFAULT_START_DATE = "1970-01-01T00:00:00Z"
DEFAULT_END_DATE = datetime.utcnow().strftime(DATE_MASK)
PER_PAGE = 100
BASE_URL = "https://api.github.com/repos/{owner}/{repo}/"
COMMITS_URL = BASE_URL + "commits{params}"
ISSUES_URL = BASE_URL + "issues{params}"

OLD_DAYS_NUM = {"pull_request": 30, "issue": 14}


def check_date(date):
    try:
        datetime.strptime(date, DATE_MASK)
        return date
    except ValueError:
        raise argparse.ArgumentTypeError("Please provide date in YYYY-MM-DDTHH:MM:SSZ format")


def check_url(url):
    if re.match('^https://github.com/[a-zA-Z0-9-]+/[a-zA-Z0-9-]+$', url):
        return url
    else:
        raise argparse.ArgumentTypeError("Url should be in https://github.com/<owner>/<repo> format")


def init_argparse() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Github repo stats"
    )
    parser.add_argument("url", help="Github repo url", type=check_url)
    parser.add_argument("-s", "--start-date", dest='start_date',
                        help="Analysis start date(default=1970-01-01T00:00:00Z)", type=check_date,
                        default=DEFAULT_START_DATE)
    parser.add_argument("-e", "--end-date", dest='end_date',
                        help="Analysis end date in YYYY-MM-DDTHH:MM:SSZ format(default=datetime.now)", type=check_date,
                        default=DEFAULT_END_DATE)
    parser.add_argument("-b", "--branch", dest='branch',
                        help="Branch for analysis(default=master)", type=str,
                        default=DEFAULT_BRANCH)
    # login, password = "","" - valid for github api authorization
    parser.add_argument("-l", "--login", help="user for github.com", type=str, default="")
    parser.add_argument("-p", "--password", help="password for github.com", type=str, default="")
    return parser


def make_params(**kwargs):
    return "?" + "&".join([f"{k}={v}" for k, v in kwargs.items() if v]) if kwargs else ""


def get_items_list(url, login, password):
    items_list = []
    while url:
        response = requests.request(
            method='GET',
            url=url,
            headers={},
            auth=requests.auth.HTTPBasicAuth(login, password)
        )
        items_list.extend(json.loads(response.text))
        url = response.links.get("next", {}).get("url", "")
        if response.status_code == 404:
            raise argparse.ArgumentTypeError("Please, make sure that branch you've chosen exists")
        if response.status_code == 403:
            raise argparse.ArgumentTypeError("Request limit")
        if response.status_code == 401:
            raise argparse.ArgumentTypeError("Wrong credentials")
    return items_list


def get_top_contributors(owner, repo, start_date, end_date, branch, login, password):
    """ print to stdout top 30 contributors for repo. Merge commits and commits without author excluded from statistics.
    :param owner: owner name
    :param repo: repository name
    :param start_date: start date for analysis
    :param end_date: end date for analysis
    :param branch: branch name for analysis
    :param login: user login for github.com
    :param password: user password for github.com
    :return: print top 30 contributors for repo with number of theirs commits
    """
    params = make_params(start_date=start_date, end_date=end_date, sha=branch, per_page=PER_PAGE)
    url = COMMITS_URL.format(owner=owner, repo=repo, params=params)
    commits = get_items_list(url, login, password)

    result = {}
    login_max_len = 0
    for commit in commits:
        author = commit.get("author", {})
        if author:
            login = author.get("login", "")
            if login not in result:
                result[login] = 0
                login_max_len = len(login) if len(login) > login_max_len else login_max_len

            if not commit.get("commit", {}).get("message", "").startswith("Merge"):
                result[login] += 1

    contributors = sorted(result.items(), key=lambda it: it[1], reverse=True)

    table_format_string = "{:" + str(login_max_len + 2) + "}{}"
    print(f"Top contributors for {branch} branch in {owner}/{repo} repository.")
    print(f"Analysis start date: {start_date}, analysis end date: {end_date}.")
    print(table_format_string.format("User login", "Number of commits"))
    for contributor_data in contributors[:30]:
        print(table_format_string.format(*contributor_data))


def get_stats(owner, repo, start_date, end_date, branch, login, password):
    """ calculate open/closed/old pull requests and issues
    :param owner: owner name
    :param repo: repository name
    :param start_date: start date for analysis
    :param end_date: end date for analysis
    :param branch: branch name for analysis
    :param login: user login for github.com
    :param password: user password for github.com
    :return: print open/closed/old pull requests and open/closed/old issues
    """

    def is_old_pr(pr_create_date, period_end_date, item_type):
        pr_create_date = datetime.strptime(pr_create_date, DATE_MASK)
        period_end_date = datetime.strptime(period_end_date, DATE_MASK)
        diff = (period_end_date - pr_create_date).days
        return diff > OLD_DAYS_NUM[item_type]

    params = make_params(state="all", base=branch, per_page=PER_PAGE)
    url = ISSUES_URL.format(owner=owner, repo=repo, params=params)
    items = get_items_list(url, login, password)

    issues = {"open": 0, "closed": 0, "old": 0}
    pull_requests = {"open": 0, "closed": 0, "old": 0}
    for item in items:
        if start_date < item.get("created_at") < end_date:
            dict_by_item_type, item_type = (
                pull_requests, "pull_request") if item.get("pull_request", "") else (issues, "issue")
            if item.get("state") == "open":
                dict_by_item_type["open"] += 1
                if is_old_pr(item.get("created_at"), end_date, item_type):
                    dict_by_item_type["old"] += 1
            if item.get("state") == "closed":
                dict_by_item_type["closed"] += 1

    print(f"Amount of open/closed/old pull requests for {branch} branch in {owner}/{repo} repository.")
    print(f"Analysis start date: {start_date}, analysis end date: {end_date}.")
    for k, v in pull_requests.items():
        print("{:8}{}".format(k, v))

    print(f"Amount of open/closed/old issues for {branch} branch in {owner}/{repo} repository.")
    print(f"Analysis start date: {start_date}, analysis end date: {end_date}.")
    for k, v in issues.items():
        print("{:8}{}".format(k, v))


def main(url, start_date, end_date, branch, login, password):
    owner, repo = url.split("/")[3:5]

    get_top_contributors(owner, repo, start_date, end_date, branch, login, password)
    get_stats(owner, repo, start_date, end_date, branch, login, password)


if __name__ == "__main__":
    parser = init_argparse()
    args = parser.parse_args()
    main(**(vars(args)))
