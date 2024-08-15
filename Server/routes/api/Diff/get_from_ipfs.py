import ipfshttpclient2
import hashlib
import base64
import json
import os
from .errors import NotFoundOnIPFS
from .text_patch import apply_patch
from .others import is_text_file
from .others import get_local_file_hash
from .others import is_file


def get_file_cid_from_patch(
        client: ipfshttpclient2.Client, 
        change_cid: str, 
        *names: str
    ) -> tuple[str]:

    files_list = client.ls(change_cid)
    hash_dict = {}
    for i in files_list["Objects"]:
        for j in i['Links']:
            if j['Name'] in names:
                hash_dict[j['Name']] = j["Hash"]
                if len(hash_dict) == len(names):
                    hashes = tuple(hash_dict[name] for name in names)
                    return hashes if len(hashes) > 1 else hashes[0]
                
    raise NotFoundOnIPFS


def get_files_type_in_patch(
        client: ipfshttpclient2.Client, 
        file_name: str, 
        change_cid: str
    ) -> bool | str:
   
    patch_cid = get_file_cid_from_patch(client, change_cid, "patch_json.json")
    json_data = client.cat(patch_cid)
    data = json.loads(json_data)

    changed_files = data["changed_files"]
    for changed_folder in changed_files.keys():
        for changed_file in changed_files[changed_folder]:
            if changed_file["sign"] == "+" or changed_file["sign"] == "?":
                new_file_path = os.path.join(changed_folder, changed_file["new_name"])
                if new_file_path == file_name:
                    return changed_file["sign"]
                    
    return False


def get_changed_file_cid_from_patch(
        client: ipfshttpclient2.Client, 
        file_name: str, 
        change_cid: str
    ) -> str:
    
    patch_cid, changes_folder_cid = get_file_cid_from_patch(client, change_cid, "patch_json.json", "changes")
    json_data = client.cat(patch_cid)
    data = json.loads(json_data)

    changed_files = data["changed_files"]

    for changed_folder in changed_files.keys():
        for changed_file in changed_files[changed_folder]:
            if (changed_file["sign"] == "+" or changed_file["sign"] == "?") and file_name == os.path.join(changed_folder, changed_file["new_name"]):
                changed_file_cid = get_file_cid_from_patch(client, changes_folder_cid, changed_file["hash"] + "." + changed_file["new_name"].split(".")[1])
                return changed_file_cid
    return ""


def get_single_text_file_ipfs(
        client: ipfshttpclient2.Client, 
        file_name: str, 
        changes_cids: list[str]
    ) -> str:
    
    files_creation_patch = -1
    for idx, change_cid in enumerate(changes_cids[::-1]):
        try:
            if get_files_type_in_patch(client, file_name, change_cid) == "+":
                files_creation_patch = idx
                break
        except NotFoundOnIPFS:
            continue
    if files_creation_patch == -1:
        raise NotFoundOnIPFS
    
    content = client.cat(get_changed_file_cid_from_patch(client, file_name, changes_cids[len(changes_cids) - files_creation_patch - 1])).decode('utf-8')

    for change_cid in changes_cids[(len(changes_cids) - files_creation_patch):]:
        patch_cid = get_changed_file_cid_from_patch(client, file_name, change_cid)

        if patch_cid == "":
            continue
        else:
            patch = client.cat(patch_cid).decode('utf-8')
            content = apply_patch(content, patch).replace("\r", "")
    return content


def get_single_not_text_file_ipfs(
        client: ipfshttpclient2.Client, 
        file_name: str, 
        changes_cids: list[str]
    ) -> str:
    
    files_creation_patch = -1
    for idx, change_cid in enumerate(changes_cids[::-1]):
        try:
            file_type_in_change = get_files_type_in_patch(client, file_name, change_cid)
            if file_type_in_change == "+" or file_type_in_change == "?":
                files_creation_patch = idx
                break
        except NotFoundOnIPFS:
            continue
    if files_creation_patch == -1:
        raise NotFoundOnIPFS
    
    content_cid = get_changed_file_cid_from_patch(client, file_name, changes_cids[len(changes_cids) - files_creation_patch - 1])            
    return content_cid



def get_project_files_patch(
        client: ipfshttpclient2.Client, 
        tree_dict: dict[str, list[str]], 
        patch_cid: str
    ) -> list[str]:    
    
    patch_cid = get_file_cid_from_patch(client, patch_cid, "patch_json.json")

    json_data = client.cat(patch_cid)
    data = json.loads(json_data.decode('utf-8'))

    for changed_dir in data["changed_folders"]:
        if (changed_dir["sign"] == "+"):
            tree_dict[changed_dir["path"]] = []
        elif (changed_dir["sign"] == "-"):
            del tree_dict[changed_dir["path"]]

    changed_files = data["changed_files"]
    for changed_folder in changed_files.keys():
        for changed_file in changed_files[changed_folder]:
            if (changed_file["sign"] == "+"):
                tree_dict[changed_folder].append(changed_file["new_name"])
                                 
            elif (changed_file["sign"] == "-"):
                tree_dict[changed_folder].remove(changed_file["old_name"])

    return tree_dict


def get_remote_project_tree(
        client: ipfshttpclient2.Client, 
        patch_cids: list[str]
    ) -> dict[str, list[str]]:
    
    tree_list = {"": []}
    for patch_cid in patch_cids:
        tree_list = get_project_files_patch(client, tree_list, patch_cid)

    return tree_list


def get_ipfs_file_hash(
        client, file_name: str, 
        changes_cids: list
    ) -> str:
    
    if not is_text_file(file_name):
        ipfs_file_cid = get_single_not_text_file_ipfs(client, file_name, changes_cids)
        file_content = base64.b64encode(client.cat(ipfs_file_cid)).decode('utf-8')
        hasher = hashlib.sha256()
        hasher.update(file_content.encode('utf-8'))
        ipfs_hash = hasher.hexdigest()
        return ipfs_hash
    
    file_content = get_single_text_file_ipfs(client, file_name, changes_cids)
    hasher = hashlib.sha256()
    file_content = file_content.replace("\r", "")
    hasher.update(file_content.encode("utf-8"))
    return hasher.hexdigest()


def compare_files_ipfs(
        client: ipfshttpclient2.Client, 
        patch_cids: list[str], 
        file_on_ipfs_name: str, 
        local_file_path: str
    ) -> bool:

    ipfs_hash = get_ipfs_file_hash(client, file_on_ipfs_name, patch_cids)
    local_hash = get_local_file_hash(local_file_path)
    return ipfs_hash == local_hash


def compare_ipfs_files(
        client: ipfshttpclient2.Client, 
        updated_patches_cids: list[str], 
        local_patches_cids: list[str], 
        file_name: str
    ) -> bool:
    updated_hash = get_ipfs_file_hash(client, file_name, updated_patches_cids)
    local_hash = get_ipfs_file_hash(client, file_name, local_patches_cids)

    return updated_hash == local_hash



def is_remote_folder_content_same(
        client: ipfshttpclient2.Client, 
        folder_path: str, 
        file_names: list[str], 
        local_folder_path: str, 
        patch_cids: list[str]
    ) -> bool:
    local_dir_files = list(filter(lambda x: is_file(x), os.listdir(local_folder_path)))

    if len(file_names) != len(local_dir_files):
        return False
    
    for file_name in file_names:
        local_file_path = os.path.join(local_folder_path, file_name)
        ipfs_file_path = os.path.join(folder_path, file_name)
        if file_name not in local_dir_files or not compare_files_ipfs(client, patch_cids, ipfs_file_path, local_file_path):
            return False
    return True


def is_remote_folder_projects_content_same(
        client: ipfshttpclient2.Client, 
        folder_path: str, 
        file_names_local: list[str], 
        file_names_cids: list[str], 
        local_patch_cides: list[str],
        updated_patch_cids: list[str]
    ) -> bool:
    if len(file_names_local) != len(file_names_cids):
        return False
    
    for file_name in file_names_local:
        file_path = os.path.join(folder_path, file_name)
        if file_name not in file_names_local or not compare_ipfs_files(client, updated_patch_cids, local_patch_cides, file_path):
            return False
    return True