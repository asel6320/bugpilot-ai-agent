"""Allowlisted GitHub API integration. No shell execution or arbitrary repository access."""
import base64, os, re, requests
API='https://api.github.com'
def config():
    repo=os.environ.get('TARGET_REPO','')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo):
        raise ValueError('TARGET_REPO must be owner/repository')
    return repo

def headers():
    token=os.getenv('GITHUB_TOKEN','')
    h={'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}
    if token: h['Authorization']='Bearer '+token
    return h

def request(method,path,**kw):
    r=requests.request(method,API+path,headers=headers(),timeout=20,**kw)
    r.raise_for_status();return r.json()

def get_file(path):
    if path!='app.py': raise ValueError('File path not allowlisted')
    data=request('GET',f'/repos/{config()}/contents/{path}')
    return base64.b64decode(data['content']).decode('utf-8'),data['sha']

def publish_pr(patched,expected_sha,run_id):
    if not os.getenv('GITHUB_TOKEN'): raise RuntimeError('GITHUB_TOKEN required for publishing')
    repo=config(); info=request('GET',f'/repos/{repo}')
    default=info['default_branch']
    head=request('GET',f'/repos/{repo}/git/ref/heads/{default}')['object']['sha']
    branch='bugpilot/fix-'+re.sub('[^a-z0-9-]','',run_id.lower())[:35]
    request('POST',f'/repos/{repo}/git/refs',json={'ref':'refs/heads/'+branch,'sha':head})
    # The file SHA is a concurrency guard; GitHub rejects stale file updates.
    request('PUT',f'/repos/{repo}/contents/app.py',json={
        'message':'fix: handle demo exception', 'content':base64.b64encode(patched.encode()).decode(),
        'branch':branch,'sha':expected_sha})
    pr=request('POST',f'/repos/{repo}/pulls',json={
        'title':'fix: handle demo exception',
        'head':branch,'base':default,
        'body':'BugPilot automated proposal. Human approved. Static checks only; GitHub Actions must run regression tests before merge.'})
    return pr['html_url']
