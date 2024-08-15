from flask import send_from_directory
import os
from flask import Blueprint
import flask

webapp_blueprint = Blueprint('webapp', __name__)


build_dir = "../WebApp/build"

@webapp_blueprint.route('/', defaults={'path': ''})
@webapp_blueprint.route('/<path:path>')
def serve(path: str) -> flask.Response:
    if path != "" and os.path.exists(build_dir + '/' + path):
        return send_from_directory(build_dir, path)
    else:
        return send_from_directory(build_dir, 'index.html')
