#!/usr/bin/env python

# Reference from https://gist.github.com/panuta/3075882

# ============================
# Requirements
# ============================
# virtualenvwrapper
# GitPython
# MySQL-python
# psycopg2


import os, sys, shutil, pwd, grp, git, subprocess, shlex, argparse, getpass
import MySQLdb as db

# ============================
# Server Settings
# ============================

    
settings = {
    'web_root': '/web',
    'git_username': 'opendream',
    'domain': 'opendream.in.th',
    'nginx_conf_file': '/etc/nginx/sites-available/%s',
    'uwsgi_conf_file': '/etc/uwsgi/apps-available/%s.xml',
    'db_username': 'root',
    'db_password': ''
}

password_file = '/tmp/deploy.auth'
if not os.path.exists(password_file):
    f = open(password_file, 'w')
    settings['db_password'] = getpass.getpass('Enter your database password for this first time : ') 
    f.write(settings['db_password'])
    f.close()

else:
    f = open(password_file, 'r')
    settings['db_password'] = f.read()
    f.close()

# ============================
# Argument from command line
# ============================

parser = argparse.ArgumentParser(description='Faster deploy script for Django project.')
parser.add_argument('repo_name', type=str)
parser.add_argument('op', type=str, help='operation init | update | delete')
parser.add_argument('--git', dest='git_url', help='specification git url (default: https://github.com/%s/%s.git)' % (settings['git_username'], '[repo_name]'))
parser.add_argument('--db_backend', dest='db_backend', help='database backend mysql | postgres (default: mysql)')
args = parser.parse_args()

repo_name = args.repo_name 
op = args.op
git_url = args.git_url or 'https://github.com/%s/%s.git' % (settings['git_username'], repo_name)
db_backend = args.db_backend or 'mysql'


# ============================
# Core
# ============================

def execute(settings, repo_name, op, git_url):

    # ============================
    # Setup folder structure
    # ============================

    project_dir = '%s/%s' % (settings['web_root'], repo_name)

    if db_backend == 'mysql':
        con = db.connect(user=settings['db_username'], passwd=settings['db_password'])
        cur = con.cursor()
    elif db_backend == 'postgres':
        # TODO
        pass

    if op == 'delete':
        if not os.path.isdir(project_dir):
            raise Exception('Project %s dose not exist' % repo_name)
        else:
            confirm_git_username  = raw_input('Enter your default git username ? ')
            if confirm_git_username != settings['git_username']:
                print 'Your default git username is %s. Please, try agian later.' % settings['git_username']
                return False

            shutil.rmtree(project_dir)
            os.remove(settings['uwsgi_conf_file'] % repo_name)
            os.remove(settings['nginx_conf_file'] % repo_name)
            subprocess.check_call(['service', 'uwsgi', 'restart'])
            subprocess.check_call(['service', 'nginx', 'restart'])
            cur.execute('DROP DATABASE %s;' % repo_name)
            con.close()

        return True
            
    
    if op == 'init':
        if os.path.isdir(project_dir):
            raise Exception('Project %s exist' % repo_name)
        else:
            # mkdir logs public_html source
            os.makedirs('%s/%s' % (project_dir, 'logs'))
            os.makedirs('%s/%s' % (project_dir, 'public_html'))
            os.makedirs('%s/%s' % (project_dir, 'source'))

    # ============================
    # Get source code
    # ============================
    source_dir = '%s/source/%s' % (project_dir, repo_name)
    if os.path.isdir(source_dir):
        g = git.cmd.Git(source_dir)
        g.pull()
        #subprocess.check_call(['git', 'pull', '--work-tree=%s' % source_dir])
    else:
        #git.Git().clone(git_url, source_dir, progres=True)
        subprocess.check_call(['git', 'clone', git_url, source_dir])

    settings_local_file = '%s/%s/settings_local.py' % (source_dir, repo_name)
    if not os.path.exists(settings_local_file):

        f = open(settings_local_file, 'w')
        f.write('''
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.%s',
        'NAME': '%s',
        'USER': '%s',
        'PASSWORD': '%s',
        'HOST': '',
        'PORT': '',
    }
}           
        ''' % ('mysql', repo_name, settings['db_username'], settings['db_password']))
        f.close()

    uid = pwd.getpwnam('www-data').pw_uid
    gid = grp.getgrnam('www-data').gr_gid
    os.chown(settings['web_root'], uid, gid)    

    # ============================
    # Setup virtualenv
    # ============================
    if not os.path.isdir('%s/bin' % project_dir):
        subprocess.check_call(['virtualenv', project_dir])

    # ============================
    # Config nginx
    # ============================
    nginx_conf_file = settings['nginx_conf_file'] % repo_name
    if not os.path.exists(nginx_conf_file):

        f = open(nginx_conf_file, 'w')
        f.write('''
server {
    listen          80;
    server_name     %s.%s;
    access_log /web/%s/logs/access.log;
    error_log /web/%s/logs/error.log;

    location / {
        uwsgi_pass      unix:///run/uwsgi/app/%s/%s.socket;
        include         uwsgi_params;
        uwsgi_param     UWSGI_SCHEME $scheme;
        uwsgi_param     SERVER_SOFTWARE    nginx/$nginx_version;
    }

    location /static {
        autoindex on;
        root   /web/%s/public_html/static;
    }

    location /media {
        autoindex on;
        root   /web/%s/source/%s;
    }

}
        ''' % (repo_name, settings['domain'], repo_name, repo_name, repo_name, repo_name, repo_name, repo_name, repo_name))
        f.close()

    nginx_enabled_file = '/etc/nginx/sites-enabled/%s' % repo_name 
    if not os.path.exists(nginx_enabled_file):
        os.symlink(nginx_conf_file, nginx_enabled_file)


    # ============================
    # Config uwsgi
    # ============================
    uwsgi_conf_file = settings['uwsgi_conf_file'] % repo_name
    if not os.path.exists(uwsgi_conf_file):
        f = open(uwsgi_conf_file, 'w')
        f.write('''
<uwsgi>
    <plugin>python</plugin>
    <vhost/>
    <socket>/run/uwsgi/app/%s/%s.socket</socket>
    <pythonpath>/web/%s/source/%s/</pythonpath>
    <chdir>/web/%s/source/%s/</chdir>
    <wsgi-file>/web/%s/source/%s/%s/wsgi.py</wsgi-file>
    <virtualenv>/web/%s</virtualenv>
    <logto>/web/%s/logs/%s.log</logto>
    <master/>
    <processes>4</processes>
    <harakiri>60</harakiri>
    <reload-mercy>8</reload-mercy>
    <cpu-affinity>1</cpu-affinity>
    <stats>/tmp/stats.socket</stats>
    <max-requests>2000</max-requests>
    <limit-as>512</limit-as>
    <reload-on-as>256</reload-on-as>
    <reload-on-rss>192</reload-on-rss>
    <no-orphans/>
    <vacuum/>
</uwsgi>
        ''' % ((repo_name, )*12))
        f.close()

    uwsgi_enabled_file = '/etc/uwsgi/apps-enabled/%s.xml' % repo_name
    if not os.path.exists(uwsgi_enabled_file):
        os.symlink(uwsgi_conf_file, uwsgi_enabled_file)

    # ============================
    # Restart Server
    # ============================

    if op == 'init':
        cur.execute('CREATE DATABASE %s DEFAULT CHARACTER SET utf8 DEFAULT COLLATE utf8_general_ci;' % repo_name)
        con.close()

    if os.path.exists('%s/requirements.txt' % source_dir):
        subprocess.check_call(['%s/bin/pip' % project_dir, 'install', '-r', '%s/requirements.txt' % source_dir, '--exists-action=i'])

    subprocess.check_call(['%s/bin/python' % project_dir, '%s/manage.py' % source_dir, 'syncdb'])
    freeze = subprocess.check_output(['%s/bin/pip' % project_dir, 'freeze'])
    if 'South' in freeze:
        subprocess.check_call(['%s/bin/python' % project_dir, '%s/manage.py' % source_dir, 'migrate'])


    subprocess.check_call(['%s/bin/python' % project_dir, '%s/manage.py' % source_dir, 'collectstatic'])
    subprocess.check_call(['service', 'uwsgi', 'restart'])
    subprocess.check_call(['service', 'nginx', 'restart'])

    # ============================
    # Recheck symlink
    # ============================
    if not os.path.exists('%s/public_html/static' % project_dir):
        os.makedirs('%s/public_html/static' % project_dir)
        os.symlink('%s/sitestatic' % source_dir, '%s/public_html/static/static' % project_dir)

    print '''
# ========================================================
# Please, go to your project and run command manually.
# Like below.
# ========================================================

cd %s

# Case use i18n
python manage.py compilemessages

#OR
./restart
''' % (source_dir)

execute(settings, repo_name, op, git_url)
