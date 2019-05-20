#activate_this = '/var/www/catalog/catalog/venv3/bin/activate_this.py'
#with open(activate_this) as file_:
 #   exec(file_.read(), dict(__file__=activate_this))

#!/usr/bin/python3
import sys
import logging
logging.basicConfig(stream=sys.stderr)
sys.path.insert(0, "/var/www/catalog/catalog/")
sys.path.insert(1, "/var/www/catalog/")

from project import app as application
