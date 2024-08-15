import time
import os
import flask
from flask import jsonify, request
import ipfshttpclient2
from flask import Blueprint
import shutil
from .Diff.create_patch import create_project_patch_json
from .Diff.create_patch import create_project_patch_from_remote_project
import multiaddr.codecs.uint16be
import multiaddr.codecs.ip4
import multiaddr.codecs.idna
from .Diff.compare_projects import compare_remote_project_folder_changes
from .Diff.get_from_ipfs import get_single_text_file_ipfs, get_single_not_text_file_ipfs
from .Diff.get_from_ipfs import get_remote_project_tree
from .Diff.apply_patch import apply_project_patch_from_remote_project
import json
from .Diff.compare_patches import get_conflicts
from .Diff.apply_patch import apply_conflicts_configurations
from .Diff.wrappers import return_to_origin, save_path
from .Diff.others import is_text_file
from .Diff.compare_projects import is_same_project
from .Diff.create_patch import create_updates_patch_json
from .Diff.apply_patch import apply_project_patch
import webbrowser

api_routes = Blueprint('api_routes', __name__, url_prefix="/api")


class API_Context:
    def __init__(self):
        self.base_path = os.path.join(os.getcwd(), "projects")
        self.client_addr = '/ip4/127.0.0.1/tcp/5001'

    
    def get_client(self) -> ipfshttpclient2.Client:
        return ipfshttpclient2.connect(self.client_addr)
    
api_context = API_Context()


@api_routes.route('/upload', methods=['POST'])
@return_to_origin(api_context.base_path)
def upload() -> flask.Response:
    client = api_context.get_client()
    try:
        data = request.get_json()

        file_path = data['path']
        if data['path']:
            os.mkdir("Temp")
            os.chdir("Temp")
            os.mkdir("base")

            create_project_patch_json("base", file_path, "base")

            result = client.add("patch-base", recursive=True)
            ipfs_hash = result[-1]["Hash"]
            
            project_details = {
            "project-name": data["name"],
            "project-path": data["path"],
            "project-changes": [ipfs_hash],
            "hidden_local_changes": []
            }

            with open("project_details.json", 'w') as json_file:
                json.dump(project_details, json_file, indent=4)
            os.rmdir("base")
            os.mkdir("changes")
            os.chdir("..")
            os.rename("Temp", data["name"])
            message = jsonify({'ipfsCID': ipfs_hash}), 200
        else:
            message = jsonify({'error': 'Invalid file path'}), 500
        
    except Exception as e:
        message = jsonify({'error': str(e)}), 500
    
    finally:
        client.close()
        return message
    

@api_routes.route('/download_project', methods=['POST'])
@return_to_origin(api_context.base_path)
def download_project() -> flask.Response:
    client = api_context.get_client()
    try:
        data = request.get_json()
        patches_cids = data["changes"]
        project_name = data["file_name"]
        project_path = data["path"]
        

        if (project_name not in os.listdir()):
            os.mkdir(project_name)
            os.chdir(project_name)
            project_details = {
            "project-name": project_name,
            "project-path": os.path.join(data["path"], data["file_name"]),
            "project-changes": patches_cids,
            "hidden_local_changes": []
            }

            with open("project_details.json", 'w') as json_file:
                json.dump(project_details, json_file, indent=4)
            os.mkdir("changes")

        os.chdir(project_path)
        if (project_name not in os.listdir()):
            os.mkdir(project_name)
            os.chdir(project_name)

            project_tree = get_remote_project_tree(client, patches_cids)
            
            folders = sorted(project_tree.keys(), key=lambda x: x.count("\\"))
            
            for folder_name in folders:
                if folder_name != "":
                    os.mkdir(folder_name)
            
            for folder in folders:
                for file_name in project_tree[folder]:
                    file_path = os.path.join(folder, file_name)
                    if is_text_file(file_path):
                        file_temp = get_single_text_file_ipfs(client, file_path, patches_cids)
                        with open(file_path, 'w') as new_file:
                            new_file.write(file_temp)
                    else:
                        file_cid = get_single_not_text_file_ipfs(client, file_name, patches_cids)
                        content = client.cat(file_cid)
                        with open(file_path, "wb") as photo_file:
                            photo_file.write(content)

            message = jsonify({'message': 352}), 200
        
        else:
            message = jsonify({'message': 354}), 200
    
    except Exception as e:
        print(e)
        message = jsonify({'error': str(e)}), 500

    finally:
        client.close()
        return message

@api_routes.route('/save_changes', methods=['POST'])
@return_to_origin(api_context.base_path)
def save_changes() -> flask.Response:
    try:
        client = api_context.get_client()
        data = request.get_json()
        project_name = data["name"]
        changes_cids = data["changes"]
        os.chdir(project_name)

        with open("project_details.json", 'r') as json_file:
            project_details = json.load(json_file)
            
        os.chdir("changes")
        if (unsaved_changes_internal(change_cids=changes_cids.copy(), project_path=project_details["project-path"], client=client, project_name=project_name)):
            create_project_patch_from_remote_project(client, changes_cids, project_details["project-path"], str(round(time.time())))
            message = jsonify({'message': 355}), 200
        else:
            message = jsonify({"message": 356}), 200
            
    except Exception as e:
        print(e)
        message = jsonify({'error': str(e)}), 500
    
    finally:
        client.close()
        return message


@api_routes.route('/get_my_changes', methods=['POST'])
@return_to_origin(api_context.base_path)
def get_my_changes() -> flask.Response:
    client = api_context.get_client()
    try:
        data = request.get_json()
        project_name = data["name"]
        project_patches = data["patches"]
        if project_name in os.listdir():
            os.chdir(project_name)

            with open("project_details.json", 'r') as json_file:
                project_details = json.load(json_file)

            my_changes = os.listdir("changes")
            un_saved_changes = unsaved_changes_internal(change_cids=project_patches, project_path=project_details["project-path"], client=client, project_name=project_name)
            hidden_local_changes = project_details["hidden_local_changes"]
            my_changes = list(filter(lambda x: x not in hidden_local_changes, my_changes))
            message = jsonify({'my_changes': my_changes, "unSavedChanges": un_saved_changes}), 200
        else:
            message = jsonify({'message': 353}), 200
            
    except Exception as e:
        print(e)
        message = jsonify({'error': str(e)}), 500

    finally:
        return message
    

@api_routes.route('/accept_change', methods=['POST'])
@return_to_origin(api_context.base_path)
def accept_change() -> flask.Response:
    try:
        data = request.get_json()
        project_name = data["name"]
        new_patch = data["patch"]
        os.chdir(project_name)

        with open("project_details.json", 'r') as json_file:
            project_details = json.load(json_file)

        project_details["project-changes"].append(new_patch)

        with open("project_details.json", 'w') as json_file:
            json.dump(project_details, json_file, indent=4)
        
        message = jsonify({'message': "success"}), 200

    except Exception as e:
        message = jsonify({'error': str(e)}), 500

    finally:
        return message
    

@save_path(api_context.base_path)
def unsaved_changes_internal(change_cids: list[str], project_path: str, client: ipfshttpclient2.Client, project_name: str) -> flask.Response:
    os.chdir(project_name)
    os.chdir("changes")
    
    my_changes = os.listdir()
    if (len(my_changes) != 0):
        last_change = max(my_changes, key=lambda x: int(x.split("-")[1]))
        result = client.add(last_change, recursive=True)
        change_hash = result[-1]["Hash"]
        if change_hash not in change_cids:
            change_cids.append(change_hash)

    same_project = is_same_project(client, change_cids, project_path)
    return not same_project


@api_routes.route('/upload_changes', methods=['POST'])
@return_to_origin(api_context.base_path)
def upload_changes() -> flask.Response:
    try:
        client = api_context.get_client()
        data = request.get_json()
        project_name = data["name"]
        change_name = data["change_name"]
        os.chdir(project_name)
        with open("project_details.json", 'r') as json_file:
            project_details = json.load(json_file)
    
        if not unsaved_changes_internal(change_cids=project_details["project-changes"].copy(), project_path=project_details["project-path"], client=client, project_name=project_name):
            my_changes = os.listdir("changes")
            selected_save = my_changes.index(change_name)
            result = client.add(os.path.join("changes", my_changes[selected_save]), recursive=True)
            ipfs_hash = result[-1]["Hash"]
            message = jsonify({'ipfsCID': ipfs_hash}), 200
            project_details["hidden_local_changes"].append(my_changes[selected_save])

            with open("project_details.json", 'w') as json_file:
                json.dump(project_details, json_file, indent=4)
        else:
            message = jsonify({'unsaved changes': 357}), 500
            
    except Exception as e:
        message = jsonify({'error': str(e)}), 500
    
    finally:
        client.close()
        return message
    
    
@api_routes.route('/search_conflicts', methods=['POST'])
@return_to_origin(api_context.base_path)
def search_conflicts() -> flask.Response:
    client = api_context.get_client()
    data = request.get_json()
    changes_cids = data["changes"]
    project_name = data["name"]
    if project_name in os.listdir():
        os.chdir(project_name)

        with open("project_details.json", 'r') as json_file:
            project_details = json.load(json_file)
        
        if (project_details["project-changes"] != changes_cids):
            local_project_changes = project_details["project-changes"]

            os.chdir("changes")
            my_changes = os.listdir()
            if (len(my_changes) != 0):
                last_change = max(my_changes, key=lambda x: int(x.split("-")[1]))
                result = client.add(last_change, recursive=True)
                last_change_cid = result[-1]["Hash"]
                conflicts = get_conflicts(client, last_change_cid, local_project_changes, changes_cids)

                if not conflicts:
                    message = jsonify({'conflicts': None, 'message': 351}), 200
                else:
                    message = jsonify({'conflicts': conflicts, 'message': 351}), 200
        else:
            message = jsonify({'message': 354}), 200
    else:
        message = jsonify({'message': 353}), 200    
    return message



@api_routes.route('/update_project', methods=['POST'])
@return_to_origin(api_context.base_path)
def update_project() -> flask.Response:
    client = api_context.get_client()
    try:
        data = request.get_json()
        changes_cids = data["changes"]
        project_name = data["name"]
        conflicts = data["conflicts"]

        os.chdir(project_name)
        
        with open("project_details.json", 'r') as json_file:
            project_details = json.load(json_file)

        local_project_changes = project_details["project-changes"]
        os.mkdir("cache")
        os.chdir("cache")
        create_updates_patch_json(client, "update", changes_cids, local_project_changes)
        apply_project_patch(project_details["project-path"], os.listdir()[0], conflicts)
        apply_conflicts_configurations(client, project_details["project-path"], local_project_changes, changes_cids, conflicts)
        message = jsonify({'message': 352}), 200

        os.chdir("..")
        project_details["project-changes"] = changes_cids
        with open("project_details.json", 'w') as json_file:
            json.dump(project_details, json_file, indent=4)

    except Exception as e:
        print(e)
        message = jsonify({'error': str(e)}), 500
    
    finally:
        client.close()
        return message    
    

@api_routes.route('/check-project', methods=['POST'])
@return_to_origin(api_context.base_path)
def check_project() -> flask.Response:
    api_context.get_client()
    try:
        data = request.get_json()
        changes_cids = data["changes"]

        if (data["name"] not in os.listdir()):
            message = {'message': 353}
        else:
            os.chdir(data["name"])
            with open("project_details.json", 'r') as json_file:
                project_details = json.load(json_file)
            if (project_details["project-changes"] == changes_cids):
                message = {'message': 354}
            else:
                message = {'message': 351}

        message = jsonify(message), 200
    except Exception as e:
        message = jsonify({'error': str(e)}), 500
    finally:
        return message
    

def get_project_files_internal(changes_cids: list[str], client: ipfshttpclient2.Client) -> list:
    project_tree = get_remote_project_tree(client, changes_cids)
    project_tree_list = []
    for folder in project_tree.keys():
        folder_files = [os.path.join(folder, file_name) for file_name in project_tree[folder]]
        folder_files.append(folder)
        project_tree_list.extend(folder_files)
    
    project_tree_list.remove("")
    return project_tree_list


@api_routes.route('/get_project_files', methods=['POST'])
@return_to_origin(api_context.base_path)
def get_project_files() -> flask.Response:
    client = api_context.get_client()
    try:
        data = request.get_json()
        changes_cids = data["changes"]
        all_files = get_project_files_internal(changes_cids, client)
        message = jsonify({"files": all_files}), 200
    except Exception as e:
        message = jsonify({'error': str(e)}), 500
    finally:
        client.close()
        return message
    
    
@api_routes.route('/get_file', methods=['POST'])
def get_single_file() -> flask.Response:
    client = api_context.get_client()
    try:
        data = request.get_json()
        changes_cids = data["changes"]
        file_name = data["file_name"]
        
        if is_text_file(file_name): 
            version = get_single_text_file_ipfs(client, file_name, changes_cids)
            message = jsonify({'file': version}), 200
        else: 
            version = get_single_not_text_file_ipfs(client, file_name, changes_cids)
            message = jsonify({'cid': version}), 200
    except Exception as e:
        message = jsonify({'error': str(e)}), 500
    finally:
        client.close()
        return message
    

@api_routes.route('/getLocalProjects', methods=['GET'])
@return_to_origin(api_context.base_path)
def getLocalProjects() -> flask.Response:
    api_context.get_client()
    try:
        local_projects = os.listdir()
        message = jsonify({'projects': local_projects}), 200
    except Exception as e:
        message = jsonify({'error': str(e)}), 500
    return message


@api_routes.route('/delete_change', methods=['POST'])
@return_to_origin(api_context.base_path)
def delete_change() -> flask.Response:
    client = api_context.get_client()
    try:
        data = request.get_json()
        change_name = data["change_name"]
        project_name = data["name"]
        
        os.chdir(project_name)
        os.chdir("changes")
        shutil.rmtree(change_name)
        message = jsonify({'message': "success"}), 200
    except Exception as e:
        print(e)
        message = jsonify({'error': str(e)}), 500
    finally:
        client.close()
        return message
    

@api_routes.route('/accept_remove', methods=['POST'])
@return_to_origin(api_context.base_path)
def accept_remove() -> flask.Response:
    try:
        data = request.get_json()
        project_name = data["name"]
        new_patch = data["patch"]
        os.chdir(project_name)

        with open("project_details.json", 'r') as json_file:
            project_details = json.load(json_file)

        project_details["project-changes"].remove(new_patch)

        with open("project_details.json", 'w') as json_file:
            json.dump(project_details, json_file, indent=4)
        
        message = jsonify({'message': "success"}), 200

    except Exception as e:
        message = jsonify({'error': str(e)}), 500

    finally:
        return message

