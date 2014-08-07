# Reference
https://gist.github.com/panuta/3075882

# Install
pip install -r requirements.txt  
cp django-deploy.py /usr/bin/

# Example
./django-deploy.py new_project init  
./django-deploy.py new_project init --git=https://bitbucket.org/username/new_project_other_name.git  
./django-deploy.py new_project update  
./django-deploy.py new_project delete  

# Document
./django-deploy.py --help

# TODO
- Postgres integration
- Unittest integration
- Production integration
