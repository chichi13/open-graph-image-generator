import os

from fastapi.templating import Jinja2Templates

TEMPLATE_DIR_NAME = "templates"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, TEMPLATE_DIR_NAME)

templates = Jinja2Templates(directory=TEMPLATES_DIR)
