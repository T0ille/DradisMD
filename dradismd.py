#!/usr/bin/env python
"""
Toolbox to export import from Dradis to a local textile/markdown files, export files to a project directly, upload attachments to a project
and handle name/path in content blocks and finding

"""
import sys
import re
import html
import argparse
import configparser
import logging
import pypandoc
import timeago
import requests
from pathlib import Path
from datetime import datetime

# Dradis API wrapper from https://github.com/NorthwaveSecurity/dradis-api
from dradis import Dradis

# Rich for output styling  https://rich.readthedocs.io/en/stable/introduction.html
from rich.console import Console
from rich.theme import Theme
from rich.filesize import decimal
from rich.markup import escape
from rich.text import Text
from rich.table import Table
from rich.tree import Tree
from rich.progress import Progress
from rich.logging import RichHandler

# colorful debug traces
from rich.traceback import install

install()

#####################################################
#                                                   #
#           DEFINITION OF CONST                     #
#                                                   #
#####################################################

DRADISMD_VERSION = "0.2.0"

SCRIPT_PATH = Path(__file__).parent  # location of dradismd.py
CONFIG_FILE = Path(f"{SCRIPT_PATH}/config.ini")  # location of config file
DATE_FORMAT = "%d/%m/%Y %H:%M"  # 17/10/2021 16:31
LINE_RETURN = "\n"  # force UNIX line return when writing files

ISSUE_TEMPLATE = Path(f"{SCRIPT_PATH}/issue_template.textile")  # location of issue template
EVIDENCE_TEMPLATE = Path(f"{SCRIPT_PATH}/evidence_template.textile")  # location of evidence template

DRADIS_FORMAT = "textile"
SUPPORTED_INPUT = [".textile", ".md"]  # input formats for pandoc
SUPPORTED_FORMAT = {  # supported format for convertion
    "textile": ".textile",  # "format name":"file extension"
    "markdown": ".md",
    "pdf": ".pdf",
    "word": ".docx",
}


# PRINT STYLES
OUTPUT_STYLE = {
    "success": "green",
    "warning": "bold orange1",
    "error": "bold red",
    "debug": "bold misty_rose1",
    "title": "bold white on blue",
    "highlight": "bright_cyan",
    "args": "bright_yellow",
}

console = Console(theme=Theme(OUTPUT_STYLE))

FORMAT = "%(message)s"
logging.basicConfig(level="CRITICAL", format=FORMAT, datefmt="[%X]", handlers=[RichHandler()])
log = logging.getLogger("rich")
logging.getLogger("requests").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)

TITLE_REGEX = f"#\[Title]#+[\r\n]+([^\r\n]+)"  # Regex to grab Title value from Dradis content
EVIDENCE_ID_REGEX = f"#\[EvidenceID]#+[\r\n]+([^\r\n]+)"
FIELD_REGEX = f"(#\[?.*\]#)+[\r\n]+([^\r\n]+)"  # Regex to grab any field value from Dradis content
NOW = datetime.now()


#####################################################
#                                                   #
#               READ CONFIG FILE                    #
#                                                   #
#####################################################


try:
    config = configparser.ConfigParser()

    if not CONFIG_FILE.is_file():
        log.error(f"The config file [{CONFIG_FILE}] is missing.")
        raise SystemExit
    else:
        config.read(CONFIG_FILE)
        API_TOKEN = config["DRADIS"]["api_token"]
        INSTANCE_URL = config["DRADIS"]["instance_url"]
        LOG_LEVEL = int(config["SETTINGS"]["log_level"])
        DEFAULT_FORMAT = config["SETTINGS"]["preferred_format"]  #

        if DEFAULT_FORMAT not in SUPPORTED_FORMAT:
            log.warning(f"{DEFAULT_FORMAT} is not supported")
            DEFAULT_FORMAT = DRADIS_FORMAT
        # Set log level
        if LOG_LEVEL > 1:
            log.setLevel(logging.DEBUG)
        elif LOG_LEVEL == 1:
            log.setLevel(logging.INFO)
        else:
            log.setLevel(logging.ERROR)

        try:
            VERIFY_SSL = config["SETTINGS"]["ssl_certificate"]  # path to certfile for manual SSL validation
            if VERIFY_SSL.lower() == "false":
                log.warning(f"⚠️ DISABLING SSL VERIFICATION ⚠️ Should only be used for testing")
                VERIFY_SSL = False
                import urllib3

                urllib3.disable_warnings()
            elif VERIFY_SSL == "":
                VERIFY_SSL = True
            elif not Path(VERIFY_SSL).is_file():
                log.warning(f"The SSL certificate {VERIFY_SSL} was not found, enabling default SSL behavior")
                VERIFY_SSL = True
        except:
            # if ssl_certificate key is missing/error reading file, enable verification
            log.warning("The SSL certificate could not be loaded, enabling default SSL behavior")
            VERIFY_SSL = True


except KeyError as e:
    log.error(f"Key not found: {e}")


#####################################################
#                                                   #
#                   Dradis API Class                #
#                                                   #
#####################################################
NO_RESULT = "ActiveRecord::RecordNotFound"


class DradisMD:
    def __init__(self, api_token, url, ssl):
        self.api = Dradis(api_token, url, ssl)
        self.projects = {}
        self.issue_list = {}
        self.dradis_nodes = {}
        self.issue_library = {}

    def list_projects(self, head: int):
        """List all Dradis project
        param head: Show only Top n project (optional)
        """
        log.debug(f"Listing Dradis Projects")
        self.projects = self.api.get_all_projects()

        # Sort projects by last updated
        sorted_projects = sorted(self.projects, key=lambda k: k["updated_at"], reverse=True)

        # Get only top X project
        if head > 0 and head < len(sorted_projects):
            sorted_projects = sorted_projects[: int(head)]

        # Logs for debug
        log.debug(sorted_projects)

        # Table of projects - Columns
        project_list_table = Table(show_header=True, header_style="bold white on blue")
        project_list_table.add_column("ID", style="cyan", width=4, justify="center")
        project_list_table.add_column("Name")
        project_list_table.add_column("Client")
        project_list_table.add_column("Last update", style="dim")

        # Add optional columns to show from custom fields in config.ini
        custom_fields = config["SETTINGS"].get("custom_fields", None)
        custom_columns = [x.strip() for x in custom_fields.split(",")]

        for column in custom_columns:
            if column.strip() != "":
                project_list_table.add_column(column)

        # Table of projects -  Rows
        for project in sorted_projects:
            if "client" in project:
                client = f"{project['client']['name']}"
            else:
                client = f"[warning]none[/warning]"

            updated_date = datetime.fromisoformat(project["updated_at"][:-1])
            time_ago = timeago.format(updated_date, NOW)
            updated_date = updated_date.strftime(DATE_FORMAT)

            new_row = (
                f"{project['id']}",
                f"{project['name']}",
                f"{client}",
                f"{updated_date} ({time_ago})",
            )

            # Get values for custom columns
            for column in custom_columns:
                if column.strip() != "":
                    field = next(
                        (field for field in project["custom_fields"] if field["name"] == column),
                        None,
                    )
                    if field:
                        value = (f"{field.get('value', None)}",)
                    else:
                        value = ("",)
                    new_row = new_row + value

            project_list_table.add_row(*new_row)

        # Print table with the list of projects
        console.print(project_list_table)

    #####################################################
    #                                                   #
    #                  Import functions                 #
    #                                                   #
    #####################################################
    def import_content_blocks(self, project_path: Path, project_id: id, format):
        """Import all content blocks
        param project_path: Folder where to create local files
        param project_id: Dradis Project id
        param format: Format for convertion
        """
        # import attachements not implemented in Dradis official API :/
        path = Path(f"{project_path}/Content Blocks")
        path.mkdir(exist_ok=True)

        content_blocks = self.api.get_all_contentblocks(project_id)
        log.debug(f"Import Report Content blocks\n")
        for block in content_blocks:
            log.debug(f"Creating file for {block['fields']['Title']} Sections Length: {len(block['content'])}")
            filename = f"{clean_filename(block['fields']['Title'])}.textile"
            file = Path(f"{path}/{filename}")
            file.write_text(block["content"], encoding="utf8", errors="ignore", newline=LINE_RETURN)
            if format != DRADIS_FORMAT:
                convert_file(file, DRADIS_FORMAT, format, True)

            log.info(f"Bloc [{Path(filename).stem}] was created")

    def import_document_properties(self, project_path: Path, project_id: int):
        log.debug(f"Import Document Properties\n")
        document_properties = self.api.get_all_docprops(project_id)
        log.debug(document_properties)
        file = Path(f"{project_path}/document_properties.ini")
        file_content = "[DOCUMENT_PROPERTIES]\n"
        for document_property in document_properties:
            for key, value in document_property.items():
                file_content = f"{file_content}{key}={value}\n"
        file.write_text(file_content, encoding="utf8", errors="ignore", newline=LINE_RETURN)
        log.info(f"document_properties.ini was created")

    def import_issues(self, path: Path, project_id: int, format: str):
        log.debug(f"\n")

        path = Path(f"{path}/Issues")
        path.mkdir(exist_ok=True)

        if not self.issue_list:
            self.issue_list = self.api.get_all_issues(project_id)

        for issue in self.issue_list:
            title = issue["title"]
            issue_content = issue["text"]
            filename = f"{clean_filename(title)}.textile"

            log.debug(f"Creating file for {title} Sections Length: {len(issue_content)}")

            file = Path(f"{path}/{filename}")
            file.write_text(issue_content, encoding="utf8", errors="ignore", newline=LINE_RETURN)

            if format != DRADIS_FORMAT:
                convert_file(file, "textile", format, True)
            log.info(f"Issue [{Path(filename).stem}] was created")

    def import_nodes(self, path: Path, project_id: int, format: str):
        log.debug(f"Import Nodes")
        if not self.dradis_nodes:
            self.dradis_nodes = self.api.get_all_nodes(project_id)
        # log.debug(self.dradis_nodes)
        for node in self.dradis_nodes:
            node_path = Path(f"{path}/Nodes/{clean_filename(node['label'])}")
            node_path.mkdir(exist_ok=True, parents=True)

            # import the evidences
            for index, evidence in enumerate(node["evidence"]):
                issue_name = evidence["issue"]["title"]
                evidences_path = Path(f"{node_path}/Evidences/{clean_filename(issue_name)}/")
                evidences_path.mkdir(parents=True, exist_ok=True)
                evidence_content = evidence["content"]
                log.debug(f"Creating evidence file for {issue_name} Sections Length: {len(evidence_content)}")
                filename = f"Evidence-{index+1}-{clean_filename(issue_name)}.textile"
                file = Path(f"{evidences_path}/{filename}")
                log.debug(evidence_content)
                file.write_text(
                    evidence_content,
                    encoding="utf8",
                    errors="ignore",
                    newline=LINE_RETURN,
                )
                if format != DRADIS_FORMAT:
                    convert_file(file, DRADIS_FORMAT, format, True)
                log.info(f"Evidence [{Path(filename).stem}] was created")

    # def import_attachments(self,path,project_id): # Download attachments not implemented in Dradis API :/
    def import_project(self, project_id: int, destination: str, format: str):
        project = self.api.get_project(project_id)
        if project.get("message") == NO_RESULT:
            log.error(f"Project {project_id} doesn't exist or you don't have access.")
        else:
            path = destination.rstrip('"')  # strip any Windows path extra " (path with space)
            if not Path(path).is_dir():
                log.error(f"The local folder {path} does not exist")
                raise SystemExit()
            else:
                log.debug(f"Import format is {format}\n")

                foldername = clean_filename(project["name"])
                path = Path(f"{path}/{foldername}")
                path.mkdir(exist_ok=True)
                log.info(f"{project.get('name',None)} is imported from Dradis")
                self.import_content_blocks(path, project_id, format)
                self.import_document_properties(path, project_id)
                self.import_issues(path, project_id, format)
                self.import_nodes(path, project_id, format)

                # Tree output of files imported
                tree = Tree(
                    f":open_file_folder: [link file://{path}]{path}",
                    guide_style="bold bright_blue",
                )
                walk_directory(Path(path), tree)
                console.print(tree)
                console.print(f"Project {project_id} was imported ✔")

    #####################################################
    #                                                   #
    #                  Export functions                 #
    #                                                   #
    #####################################################

    def handle_attachments(self, project_id, node_id, content, file_path) -> str:
        """Upload attachments from textile content to Dradis and return the content with the updated Dradis file path"""

        existing_nodes_attachments = self.api.get_all_attachments(project_id, node_id)
        r = re.compile("(?P<match>!(?P<path>.*?)(?P<caption>\(.*?)?!)")  #  !/path/attachments(optional_caption)!
        attachments = [m.groupdict() for m in r.finditer(content)]
        if attachments:
            log.debug(f"handling attachment: {attachments}")
            dradis_dir = f"/pro/projects/{project_id}/nodes/{node_id}/attachments"
            files = []
            already_existed = []
            for attachment in attachments:
                attachment_path = Path(attachment.get("path"))
                log.debug(existing_nodes_attachments)

                # check if file to upload already exists
                if not any(
                    d["filename"] == attachment_path.name.replace("%20", " ") for d in existing_nodes_attachments
                ):
                    full_attachments_path = Path.resolve(
                        Path.joinpath(file_path, attachment_path.as_posix().replace("%20", " "))
                    )
                    if not full_attachments_path.is_file():
                        log.warning(f"{full_attachments_path} was not found. File missing? Skipping")
                        continue
                    else:
                        files.append(full_attachments_path)
                else:
                    already_existed.append(attachment_path.name)

                # Replace the name of the file with dradis format
                caption = attachment.get("caption", None)
                log.debug(f"Upload of {attachment_path.name}")
                if caption:
                    content = re.sub(
                        re.escape(attachment.get("match")),
                        f"!{dradis_dir}/{attachment_path.name}{caption}!",
                        content,
                    )
                else:
                    content = re.sub(
                        re.escape(attachment.get("match")),
                        f"!{dradis_dir}/{attachment_path.name}!",
                        content,
                    )
            if already_existed:
                log.debug(
                    f"The following attachments {attachment_path.name} already existed on this Dradis node and were not uploaded."
                )
            # Upload files to dradis
            if files:
                self.api.create_attachment(project_id, node_id, *files)
        return content

    def export_content_block(self, project_id, file):
        """
        Export content block file to Dradis
        """
        # Check if valid file and convert it to textile string
        content = get_textile_content(file)
        if content:
            # Check if #[Title]#  is present ( = valid file to export)
            title = get_title(content)
            if not title:
                log.warning(f"{file.name} does not have a #[Title]# field, skipping ")
            # Valid file
            else:
                node_id = self.get_node_id_from_file(project_id, file)
                content = self.handle_attachments(project_id, node_id, content, file.parent)
                dradis_content_blocks = self.api.get_all_contentblocks(project_id)

                title_found = get_item_from_dict_list(dradis_content_blocks, "title", title)

                # create new block
                if not title_found:
                    log.info(f"Creating content block {title}")
                    result = self.api.create_contentblock(project_id, content, title)

                # update existing block
                else:
                    log.info(f"Updating content block {title}")
                    block_id = title_found["id"]
                    result = self.api.update_contentblock(project_id, block_id, content)
                log.debug(result)

    def export_document_properties(self, project_id, path):
        properties_file = configparser.ConfigParser()
        properties_file.read(path)
        properties = dict(properties_file["DOCUMENT_PROPERTIES"])
        for key, value in properties.items():
            try:
                result = self.api.update_docprop(project_id, key, value)
                log.debug(result)  # debug logs
            except:
                log.error(f"Property {key} failed to update")
        log.info("Document Properties exported")

    def export_issue(self, project_id, file):
        content = get_textile_content(file)
        if content:
            title = get_title(content)
            if not title:
                log.warning(f"{file.name} does not have a #[Title]# field, skipping")

            # Valid file
            else:
                if not self.issue_list:
                    self.issue_list = self.api.get_all_issues(project_id)
                issue_found = get_item_from_dict_list(
                    self.issue_list, "title", title
                )  # check if title exist already in dradis
                if not issue_found:  # create new issue
                    log.info(f"Creating issue {title}")
                    result = self.api.create_issue(project_id, content)
                    log.debug(f"result= {result}")
                else:  # update existing issue
                    log.info(f"Updating issue {title}")
                    issue_id = issue_found["id"]
                    result = self.api.update_issue(project_id, issue_id, content)
                    log.debug(f"result= {result}")

    def export_node(self, project_id, node_folder):
        if not self.dradis_nodes:
            self.dradis_nodes = self.api.get_all_nodes(project_id)

        node_found = get_item_from_dict_list(self.dradis_nodes, "label", node_folder.name)
        if not node_found:  # create new node
            log.info(f"Creating node {node_folder.name}")
            result = self.api.create_node(project_id, node_folder.name, 1)
            node_id = result["id"]
        else:  # node already exists
            log.debug(f"Found existing node {node_folder.name}")
            node_id = node_found["id"]

        # Check if evidences to be updated
        evidence_path = Path(f"{node_folder}/Evidences")
        if not evidence_path.is_dir():
            log.info(f"No Evidences folder in Node {node_folder.name}")
        else:
            log.debug("Exporting evidences")

            evidence_issue_folders = get_folders_in_folder(evidence_path)  # list of issue folders in evidence folder
            # For each issue
            for issue_folder in evidence_issue_folders:
                evidence_list_for_issue = get_files_in_folder(issue_folder)
                # For each evidence file
                for file in evidence_list_for_issue:
                    self.export_evidence(project_id, node_id, issue_folder.name, file)

    def export_evidence(self, project_id, node_id, local_issue_name, evidence_file):
        # Export evidences
        dradis_evidence_content = get_textile_content(evidence_file)
        if dradis_evidence_content:
            # check if issue folder (local) exists on Dradis
            if not self.issue_list:
                self.issue_list = self.api.get_all_issues(project_id)
            issue_found = get_item_from_dict_list(self.issue_list, "title", local_issue_name)

            if not issue_found:
                log.warning(f"The issue {local_issue_name} was not found on Dradis, skipping evidence export")
            else:

                dradis_evidence_content = self.handle_attachments(
                    project_id, node_id, dradis_evidence_content, evidence_file.parent
                )

                # Get evidence ID
                evidence_id_found = re.search(EVIDENCE_ID_REGEX, dradis_evidence_content)

                # Update evidence that has same evidenceID
                if evidence_id_found:
                    evidence_id = evidence_id_found.group(1)
                    log.debug(f"Updating evidence {evidence_id}")
                    try:
                        result = self.api.update_evidence(
                            project_id,
                            node_id,
                            issue_found["id"],
                            evidence_id,
                            dradis_evidence_content,
                        )
                        log.debug(result)

                    except:
                        log.warning(f"Could not update {evidence_id}, creating new evidenceID")
                        self.new_evidence(
                            project_id,
                            node_id,
                            issue_found["id"],
                            dradis_evidence_content,
                            evidence_file,
                            True,
                        )

                # New evidence
                else:
                    log.debug(f"No evidence ID. Creating new")
                    self.new_evidence(
                        project_id,
                        node_id,
                        issue_found["id"],
                        dradis_evidence_content,
                        evidence_file,
                    )

    def new_evidence(
        self,
        project_id,
        node_id,
        issue_id,
        dradis_evidence_content,
        evidence,
        erase_previous_id=False,
    ) -> int:
        # Create the new evidence and collect evidenceID
        result = self.api.create_evidence(project_id, node_id, issue_id, dradis_evidence_content)
        evidence_id = result.get("id", None)

        evidence_content = evidence.read_text(encoding="utf8", errors="ignore")
        if erase_previous_id:
            evidence_content = re.sub(EVIDENCE_ID_REGEX, "", evidence_content)

        # Append evidenceID to the local file : allows to update this evidence later on
        evidence.write_text(
            f"{evidence_content}\n#[EvidenceID]#\n\n{evidence_id}\n",
            encoding="utf8",
            newline=LINE_RETURN,
            errors="ignore",
        )

    def update_project(self, project_id, path):
        project = self.api.get_project(project_id)
        if project.get("message") == NO_RESULT:
            log.error(f"Project {project_id} doesn't exist or you don't have access.")
        else:
            path = Path(path.rstrip('"'))

            # Export single project file
            if path.is_file():
                self.update_item(project_id, path)
            # Export full project
            elif path.is_dir():

                log.info(f"{project['name']} is being updated on Dradis")
                content_block_path = Path(f"{path}/Content Blocks")
                if content_block_path.is_dir():
                    log.debug(f"Exporting Content blocks")
                    content_blocks_files = [f for f in Path(content_block_path).iterdir() if f.is_file()]
                    for file in content_blocks_files:
                        self.export_content_block(project_id, file)
                else:
                    log.warning(f"No Content Blocks folder found.")

                document_properties_path = Path(f"{path}/document_properties.ini")
                if document_properties_path.is_file():
                    log.debug(f"Exporting Document Properties")
                    self.export_document_properties(project_id, document_properties_path)
                else:
                    log.warning(f"No document properties found.")

                issues_path = Path(f"{path}/Issues")
                if issues_path.is_dir():
                    log.debug(f"Exporting Issues")
                    local_issues = get_files_in_folder(issues_path)
                    for file in local_issues:
                        self.export_issue(project_id, file)
                else:
                    log.warning(f"No Issues folder found.")

                nodes_path = Path(f"{path}/Nodes")
                if nodes_path.is_dir():
                    log.debug(f"Exporting Nodes")
                    local_nodes = get_folders_in_folder(nodes_path)
                    for folder in local_nodes:
                        self.export_node(project_id, folder)

                else:
                    log.warning(f"No Nodes folder found.")

                console.print(f"{project.get('name',None)} was fully updated. ✔")
            else:
                log.error(f"{path} does not exist")

    def update_item(self, project_id: int, path: Path):
        """_summary_

        Args:
            project_id (int): _description_
            path (Path): _description_
        """
        log.info(f"{path.name} is being updated to Dradis")
        if path.name == "document_properties.ini":
            self.export_document_properties(project_id, path)
        elif path.parent.name == "Content Blocks":
            self.export_content_block(project_id, path)
        elif path.parent.name == "Issues":
            self.export_issue(project_id, path)
        elif path.parent.parent.name == "Evidences":
            node_id = self.get_node_id_from_file(project_id, path)
            self.export_evidence(project_id, node_id, path.parent.name, path)

    def get_node_id_from_file(self, project_id, file_path):
        """Return corresponding node id in Dradis for specific local file. Useful to know where to upload attachments"""
        if not self.dradis_nodes:
            self.dradis_nodes = self.api.get_all_nodes(project_id)  # get list of nodes for project
        if file_path.parent.name == "Content Blocks":  # /<Project Name>/Content Blocks/file_path
            # node id for all Content Blocks is always the one before "Uploaded files" but for some reason is not listed in the list of nodes, thus we need to guess it here
            uploaded_files_node = get_item_from_dict_list(self.dradis_nodes, "label", "Uploaded files")
            node_id = f"{uploaded_files_node['id']-1}"
        elif file_path.parent.parent.name == "Evidences":  # /<Project Name>/Nodes/<Node Name>/Evidences/file_path
            evidence_node = get_item_from_dict_list(self.dradis_nodes, "label", file_path.parent.parent.parent.name)
            node_id = f"{evidence_node['id']}"
        else:
            log.error(f"Could not find node id for {file_path} ")
            return None
        return node_id

    #####################################################
    #                                                   #
    #                  List/Create Issue                #
    #                                                   #
    #####################################################

    def list_issues_in_library(self, search_term):
        if not self.issue_library:
            self.issue_library = self.api.get_all_standard_issues()

        # Table of projects - Columns
        sorted_match_table = Table(show_header=True, header_style="bold white on blue")
        sorted_match_table.add_column("ID", style="cyan", width=4, justify="center")
        sorted_match_table.add_column("Title")

        if search_term:
            from difflib import SequenceMatcher

            match_list = []
            for issue in self.issue_library:
                match = False
                average = 0
                keywords_found = []
                # Find a matching word at 80%
                for word in issue["title"].split():
                    for keyword in search_term.split():
                        # print(keyword)
                        match_ratio = SequenceMatcher(None, keyword, word).ratio()
                        if match_ratio > 0.80:
                            match = True
                            average += match_ratio
                            keywords_found.append(word)
                average = average / len(search_term.split())
                if match:
                    issue["match_ratio"] = average
                    issue["keywords"] = keywords_found
                    match_list.append(issue)

            sorted_match = sorted(list(match_list), key=lambda k: k["match_ratio"], reverse=True)
            sorted_match_table.add_column("Matching search at", style="dim")

            for issue in sorted_match:
                # highligh keyword in title
                for keyword in issue["keywords"]:
                    issue["title"] = issue["title"].replace(keyword, f"[highlight]{keyword}[/highlight]")
                sorted_match_table.add_row(
                    str(issue["id"]), issue["title"], f"{'{:.2f}'.format(issue['match_ratio']*100)} %"
                )
        else:
            for issue in self.issue_library:
                sorted_match_table.add_row(str(issue["id"]), issue["title"])
                # highlight keywords
        console.print(sorted_match_table)

    def add_issue(self, project_path, node_name, issue_title=None, issue_id=None):
        if not EVIDENCE_TEMPLATE.is_file():
            log.error(f"The template file to create an empty evidence was not found. Please check config.ini")
        else:
            # If new blank evidence from template
            if not issue_id:
                if not ISSUE_TEMPLATE.is_file():
                    log.error("The template file to create an empty issue was not found. Please check config.ini")
                else:
                    log.info(f"Creating local issue: {issue_title}")
                    issue_content = ISSUE_TEMPLATE.read_text(encoding="utf8", errors="ignore")
                    issue_content = issue_content.replace("#[Title]#", f"#[Title]#\n{issue_title}")

            # If import from library
            else:
                log.info(f"Creating local issue {issue_id}")
                issue = self.api.get_standard_issue(issue_id)
                issue_content = issue["content"]
                issue_title = clean_filename(issue["title"])

            # Create Issue
            issue_folder_path = Path(f"{project_path}/Issues")
            issue_folder_path.mkdir(exist_ok=True, parents=True)
            extension = SUPPORTED_FORMAT[DEFAULT_FORMAT]
            Path(f"{issue_folder_path}/{issue_title}{extension}").write_text(
                issue_content, encoding="utf8", newline=LINE_RETURN, errors="ignore"
            )
            # Create evidence
            if node_name:
                evidence_content = EVIDENCE_TEMPLATE.read_text(encoding="utf8", errors="ignore")
                evidence_folder_path = Path(f"{project_path}/Nodes/{node_name}/Evidences/{issue_title}")
                evidence_folder_path.mkdir(exist_ok=True, parents=True)
                evidence_file = Path(f"{evidence_folder_path}/Evidence{extension}")
                while evidence_file.is_file():
                    log.debug("Evidence file already existed, creating new one")
                    last_char = evidence_file.stem[-1:]
                    if last_char.isdigit():
                        evidence_file = Path(
                            f"{evidence_folder_path}/{evidence_file.stem[:-1]}{int(last_char)+1}{extension}"
                        )
                        log.debug(f"Evidence {evidence_file}")
                    else:
                        evidence_file = Path(f"{evidence_folder_path}/Evidence2{extension}")
                        log.debug(f"Evidence {evidence_file}")
                evidence_file.write_text(evidence_content, encoding="utf8", newline=LINE_RETURN, errors="ignore")

    #####################################################
    #                                                   #
    #                  Convert functions                #
    #                                                   #
    #####################################################


def convert_files(path, output_format=DRADIS_FORMAT):
    """Convert file or list of files to desired format
    param path: file or folder
    param output_format: format in list of supported format
    """

    # Strip Window double quote from tab completion a the end in of filepath
    path = Path(path.rstrip('"'))

    # Show Pandoc info for debug
    log.debug(f"Pandoc Version: {pypandoc.get_pandoc_version()}")
    log.debug(f"Pandoc Path: {pypandoc.get_pandoc_path()}")
    log.debug(f"Pandoc Formats: {pypandoc.get_pandoc_formats()}")

    if output_format not in SUPPORTED_FORMAT:
        log.error(f"The format '{output_format}' is not supported.")
    else:
        # Directory
        if path.is_dir():
            log.debug(f"Converting files in directory {path.name} to {output_format}")
            filelist = path.rglob("*")  # list file in directory + sub-dir
            for file in filelist:
                extension = file.suffix
                if extension in SUPPORTED_INPUT:  # only convert from files with valid markup format
                    input_format = guess_format(extension)
                    convert_file(file, input_format, output_format, False)
        # File
        elif path.is_file():
            extension = path.suffix
            if extension in SUPPORTED_INPUT:
                input_format = guess_format(extension)
                convert_file(path, input_format, output_format, False)
            else:
                log.warning(f"Extension {extension} not supported. Expecting {SUPPORTED_INPUT}")
        # Not found
        else:
            log.error(f"{path} is not a folder or file. Please provide a valid folder or file")


def pandoc_installed():
    try:
        pypandoc.get_pandoc_version()
        return True
    except:
        log.warning("Pandoc is not installed or not detected in PATH")
        return False


# Download pandoc if user wants to
def get_pandoc():
    while (res := input("Do you want pypandoc to install it for you? [Y/n]").lower()) not in {"", "y", "n"}:
        pass
    if res == "" or res[0].lower() == "y":
        # expects an installed pypandoc: pip install pypandoc
        from pypandoc.pandoc_download import download_pandoc

        # see the documentation how to customize the installation path
        # but be aware that you then need to include it in the `PATH`
        try:
            download_pandoc()
        except:
            log.error("Pandoc install could not be fully completed. Check if it correctly installed with 'pandoc -v'")
    else:
        console.print(
            "If you want to convert files, you can install pandoc manually with:\n🐧: sudo apt-get install pandoc\n🍫: choco install pandoc\n🍺: brew install pandoc pandoc-citeproc Caskroom/cask/mactex\n More info: https://pandoc.org/installing.html"
        )


def convert(content, input_format, output_format) -> str:
    """Convert markup content using pandoc"""

    import pypandoc  # file convertion https://github.com/NicklasTegner/pypandoc

    # log.debug(f"Converting {input_format} to {output_format}")

    if not pandoc_installed():
        get_pandoc()
        # TODO: check missing latex pandoc module for converting to PDF/DOCX
    else:

        disabled_pandoc_plugins = ["autolink_bare_uris", "gfm_auto_identifiers"]
        # The list of default pandoc plugin can be obtained with "pandoc --list-extensions=gfm"
        # The plugins above can be annoying when converting gfm markdown to textile, thus they are disabled.
        # autolink_bare_uris makes http://example.com --> "$":http://example.com
        # gfm_auto_identifiers add undesired name ID in headers: e.g: # Title -> h1(Title).

        if output_format == "markdown":
            output_format = "gfm"  # Force github flavored Markdown as output instead of regular markdown
        if input_format == "markdown":
            input_format = "gfm"
            for plugin in disabled_pandoc_plugins:
                input_format = f"{input_format}-{plugin}"  # disable plugins with '-'

        if input_format != output_format:
            try:
                pandoc_args = ["--wrap=none"]  # pandoc argument to pass
                content = re.sub(
                    FIELD_REGEX, f"\g<1>\r\n\r\n\g<2>", content
                )  # Make sure there is always 2 {LINE_RETURN} between #[Field]# and their content
                output = pypandoc.convert_text(content, output_format, format=input_format, extra_args=pandoc_args)
                output = replace_unecessary_escape(output)
                if output_format == "textile":
                    output = html.unescape(output)  # Unescape &
                return output
            except:
                log.error(f"Content could not be converted. Is this a valid file markup file (md/textile)?")
        else:
            log.debug(f"No converting needed for this file. Skipping")


def convert_file(file_path, input_format, output_format, delete_input_file=True):

    file_path = Path(file_path)
    output_extension = SUPPORTED_FORMAT[output_format]
    new_file = Path(f"{file_path.parent/file_path.stem}{output_extension}")

    content = file_path.read_text(encoding="utf8", errors="ignore")
    log.debug(f"File {file_path.name} --> {new_file.name} ")
    new_content = convert(content, input_format, output_format)
    new_file.write_text(new_content, encoding="utf8", newline=LINE_RETURN, errors="ignore")

    if delete_input_file:  # delete file after converting
        file_path.unlink()


def replace_unecessary_escape(text: str):
    # Pandoc has "too agressive" char escape: https://github.com/jgm/pandoc/issues/6259
    # No option allow to disable char escaping when not necessary with GFM output
    # We have to replace escaped char from the pandoc output manually
    # Eg.: \[  --> [
    text = text.replace("\<", "<")
    text = text.replace("\>", ">")
    text = text.replace("\\\\", "\\")
    text = text.replace("\*", "*")
    text = text.replace("\_", "_")
    text = text.replace("\[", "[")
    text = text.replace("\]", "]")
    text = text.replace("\#", "#")
    text = text.replace("\|", "|")
    text = text.replace("\~", "~")
    text = text.replace("\.\.", "..")
    return text


def get_textile_content(file: Path) -> str:
    """
    Read markup file and return textile content for Dradis
    """
    extension = file.suffix
    textile_content = ""
    if extension != ".textile":
        if extension in SUPPORTED_INPUT:
            log.debug(f"Reading textile from {file.name} ")
            try:

                input_format = guess_format(extension)  # get input format from file extension
                content = file.read_text(encoding="utf8", errors="ignore")
                textile_content = convert(content, input_format, "textile")

            except Exception as e:
                log.error(f"Error with get_textile_content from {file} :{e}")
                return ""
        else:
            log.warning(f"{file.name} was not a valid markup format, skipping Dradis export")
            return ""

    else:
        textile_content = file.read_text(encoding="utf8", errors="ignore")
    return textile_content

    #####################################################
    #                                                   #
    #                  Generic functions                #
    #                                                   #
    #####################################################


def get_title(content: str) -> str:
    """get title from bloc or return empty string if not found"""
    match = re.search(TITLE_REGEX, content)
    title = match.group(1)  # get section title from file
    if not match or title.startswith("#["):
        return ""
    else:
        return title


def guess_format(extension):
    """guess file format from extension of file"""
    return list(SUPPORTED_FORMAT.keys())[list(SUPPORTED_FORMAT.values()).index(extension)]


def clean_filename(filename: str) -> str:
    """Remove char from string that cant be in (Windows) file path"""
    for char in '<>:]"/\\|?*.':
        filename = filename.replace(char, "")
    return filename


def get_item_from_dict_list(dict_list: list, key_to_check: str, matching_string: str) -> dict:
    match = next(
        (
            dict
            for dict in dict_list
            if clean_filename(dict[key_to_check]).lower() == clean_filename(matching_string).lower()
        ),
        None,
    )
    return match


def get_files_in_folder(folder) -> list:
    return [f for f in Path(folder).iterdir() if f.is_file()]


def get_folders_in_folder(folder) -> list:
    return [f for f in Path(folder).iterdir() if f.is_dir()]


# tree for folder output stolen from rich repo examples: https://github.com/willmcgugan/rich/tree/master/examples
def walk_directory(directory: Path, tree: Tree) -> None:
    """Recursively build a Tree with directory contents."""
    # Sort dirs first then by filename
    paths = sorted(
        Path(directory).iterdir(),
        key=lambda path: (path.is_file(), path.name.lower()),
    )
    for path in paths:
        # Remove hidden files
        if path.name.startswith("."):
            continue
        if path.is_dir():
            style = "dim" if path.name.startswith("__") else ""
            branch = tree.add(
                f"[bold magenta]:open_file_folder: [link file://{path}]{escape(path.name)}",
                style=style,
                guide_style=style,
            )
            walk_directory(path, branch)
        else:
            text_filename = Text(path.name, "blue")
            text_filename.highlight_regex(r"\..*$", "cyan")
            text_filename.stylize(f"link file://{path}")
            file_size = path.stat().st_size
            text_filename.append(f" ({decimal(file_size)})", "dim blue")
            icon = "📄 " if path.suffix in SUPPORTED_INPUT else "⚙ " if path.suffix == ".ini" else "❔ "
            tree.add(Text(icon) + text_filename)


def test_connection(url):
    accepted_code = [200, 302]
    timeout_time = 10
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0"
    req_headers = {"User-Agent": ua}
    try:
        resp = requests.get(
            url=url,
            allow_redirects=True,
            headers=req_headers,
            timeout=timeout_time,
            verify=VERIFY_SSL,
        )
    except:
        return False
    return resp.status_code in accepted_code


def rename_attachments_from_file(file_path, renaming_format):
    """Parse and rename attachments with the renaming format
    Example:
    renaming_format=[section_title]_[section]_[foldername]_[caption]

    ![Reflected XSS](/xss/202205101428.png)
    will become
    ![Reflected XSS](/xss/Attack%20Narrative_04_xss_Reflected_XSS.png)
    """

    log.info(f"Renaming attachments in {file_path}")
    if not renaming_format:
        log.error("No renaming format provided. Please check config.ini")
    else:
        log.debug(f"Using renaming format: {renaming_format}")
        work_file = Path(file_path)
        if work_file.is_file():
            content = work_file.read_text(encoding="utf8", errors="ignore")
            r = re.compile("(?P<match>!\[(?P<caption>.*?)\]\((?P<path>.*?)\))")  #  ![caption](image)'
            attachments = [m.groupdict() for m in r.finditer(content)]
            for index, attachment in enumerate(attachments):
                attachments_path = Path(attachment.get("path"))
                full_attachments_path = Path.joinpath(work_file.parent, attachments_path)
                if not full_attachments_path.is_file():
                    log.warning(f"{full_attachments_path} was not found. Is attachment missing?")
                else:
                    title = get_title(content)
                    if not title:
                        section_initials = "ZZZ"
                    else:
                        section_initials = "".join([x[0].upper() for x in title.split(" ")])
                    foldername = full_attachments_path.parent.parent
                    new_filename = (
                        renaming_format.replace("[section_initials]", section_initials)
                        .replace("[section_title]", title.lower())
                        .replace("[foldername]", str(foldername).lower())
                        .replace("[filename]", str(attachments_path.stem))
                        .replace("[count]", str(index + 1).zfill(3))
                        .replace("[caption]", clean_filename(attachment.get("caption")))
                    )  # .replace(" ","_")
                    new_path = f"{full_attachments_path.parent}/{new_filename}{attachments_path.suffix}"
                    relative_markdown_path = f"{attachments_path.parent.as_posix()}/{new_filename.replace(' ','%20')}{attachments_path.suffix}"
                    new_attachment = f"![{attachment.get('caption')}]({relative_markdown_path})"
                    # log.debug(attachment.get("match"))
                    log.debug(new_attachment)
                    content = content.replace(
                        attachment.get("match"),
                        new_attachment,
                    )
                    #![{caption}]({new_path})
                    full_attachments_path.rename(new_path)
            work_file.write_text(content, encoding="utf8", newline=LINE_RETURN)


def print_help():
    """Print help message"""
    help_table = Table(show_header=True, box=None, padding=(1, 2), collapse_padding=True)
    help_table.add_column("Action\n    [dim][--option][dim]", style="highlight")
    help_table.add_column("Arguments", style="args")
    help_table.add_column("Description")
    help_table.add_row("--help", "", "Show this help message")
    help_table.add_row(
        "projects\n    [dim][--head][/dim]",
        "\n[dim]<number>[/dim]",
        "List projects with their IDs in last updated order\n[dim]Show only last X projects[/dim]",
    )
    help_table.add_row(
        "get\n   [dim][--format][/dim]",
        "<project_id> <destination_folder>\n[dim]<format>",
        "Import a project from Dradis to local folder\n[dim]Format to convert to when importing[/dim]",
    )

    help_table.add_row(
        "issues\n[dim][keywords][/dim]",
        "[dim]<keywords>[/dim]",
        "List issues from issue library. \n[dim]Search the issue library  for one of the keywords provided[/dim]",
    )
    help_table.add_row(
        "add_issue \n   [dim][--node][/dim]",
        "<project_path> --id <id> or --title <title>\n[dim]<node_name>[/dim]",
        "Add an issue to project folder from template or from issue library if --id is used. \n[dim]Create a new evidence too if --node [node_name] is provided[/dim]",
    )
    help_table.add_row("update", "<project_id> <source>", "Export your local projects files to Dradis")
    help_table.add_row(
        "convert",
        "<folder|file> <format>",
        f"Convert a project file (markup format) or all project files in a folder to another supported format {list(SUPPORTED_FORMAT.keys())}",
    )
    help_table.add_row(
        "rename",
        "<input_file> <attachments_folder>",
        "Rename all attachments in a file with correct Dradis path and rename with format from config file",
    )

    console.print(help_table)
    console.print(
        "[highlight]Example of use:[/highlight]\npython dradismd.py [args]projects[/args]\npython dradismd.py [args]get 47 /workfolder/pentests [dim]--format markdown[/dim][/args]",
        style=None,
    )


def arg_parser():

    # Argument parser
    parser = argparse.ArgumentParser("", add_help=False)
    subparsers = parser.add_subparsers(title="action", description="Possible action", dest="action")

    # list projects:            list [--last <amount>]
    parser_list = subparsers.add_parser("list", aliases=("l", "lp", "project", "projects", "list_projects"))
    parser_list.set_defaults(action="list_projects")
    parser_list.add_argument("--head", action="store", type=int, nargs="?", const=5)

    # get project:           get <projectid> <path> [--format <format>]
    parser_import = subparsers.add_parser("get", aliases=("import"))
    parser_import.set_defaults(action="get")
    parser_import.add_argument("project_id", action="store")
    parser_import.add_argument("destination", action="store", nargs="?")
    parser_import.add_argument("--format", action="store", nargs="?", const=DEFAULT_FORMAT)

    # update project:           update <projectid> <file | folder>
    parser_export = subparsers.add_parser("update", aliases=("export"))
    parser_export.set_defaults(action="update")
    parser_export.add_argument("project_id", action="store")
    parser_export.add_argument("path", action="store", nargs="?")

    # list issue in library :           list_issue [keyword]
    parser_list_issues = subparsers.add_parser("issue", aliases=("list_issues", "issues", "issue", "li", "search"))
    parser_list_issues.set_defaults(action="list_issues")
    parser_list_issues.add_argument("search_term", action="store", nargs="?")

    # add local issue:           add_issue  <path> [node_name] [--format <format>]
    parser_add_issue = subparsers.add_parser("add_issue", aliases=("add", "new_issue"))
    parser_add_issue.set_defaults(action="add_issue")
    parser_add_issue.add_argument("project_path", action="store", nargs="?")
    parser_add_issue.add_argument("--node", "-n", action="store", nargs="?")
    add_issue_option = parser_add_issue.add_mutually_exclusive_group(required=True)
    add_issue_option.add_argument("--id", "-i", action="store")
    add_issue_option.add_argument("--title", "-t", action="store", const="New Issue", nargs="?")

    # convert project files:      convert <file> --format :
    parser_convert = subparsers.add_parser("convert")
    parser_convert.add_argument("path", action="store")
    parser_convert.add_argument("format", action="store")

    # rename attachments:      rename <file> <folder_with_attachments> :
    parser_rename = subparsers.add_parser("rename")
    parser_rename.add_argument("file", action="store")

    parser.add_argument("-h", "--help", action="store_true", dest="help")

    # Show help when no argument is providedt
    if len(sys.argv) <= 1:
        sys.argv.append("--help")

    # Parse script argument
    try:
        args = parser.parse_args()
    # Invalid argument
    except:
        log.error("Not a valid action or requires more arguments")
    return args


def main():
    console.print(
        f" > Dradis[bold]MD[/bold] [grey]v{DRADISMD_VERSION}[/grey]",
        style="title",
        highlight=False,
    )
    args = arg_parser()
    if args.action in ["list_projects", "get", "update", "list_issues", "add_issue"]:
        if len(config["DRADIS"]["api_token"]) != 20:
            log.error(f"Invalid or missing Dradis API token")
            raise SystemExit()
        else:
            if not test_connection(INSTANCE_URL):
                log.error(f"Instance url definied in config.ini is not reachable")
                raise SystemExit()
            else:
                dradis = DradisMD(API_TOKEN, INSTANCE_URL, VERIFY_SSL)
                log.debug("Loaded API key from config file")

    # Action handler
    if args.help:
        print_help()
    elif args.action == "list_projects":
        dradis.list_projects(args.head or 0)
    elif args.action == "get":
        dradis.import_project(args.project_id, args.destination or ".", args.format or DRADIS_FORMAT)
    elif args.action == "update":
        dradis.update_project(args.project_id, args.path or ".")
    elif args.action == "list_issues":
        dradis.list_issues_in_library(args.search_term or None)
    elif args.action == "add_issue":
        dradis.add_issue(args.project_path or ".", args.node or None, args.title or None, args.id or None)
    elif args.action == "convert":
        convert_files(args.path, args.format or DRADIS_FORMAT)
    elif args.action == "rename":
        rename_attachments_from_file(args.file, config["SETTINGS"].get("renaming_format"))
    else:
        log.error("Invalid action")


if __name__ == "__main__":
    main()
