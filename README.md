# DradisMD

Current version:    **0.2.0**
  
DradisMD allows to import, manage [Dradis](https://dradisframework.com/) projects locally and convert Dradis textile format to [GitHub Flavored Markdown](https://docs.github.com/en/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/basic-writing-and-formatting-syntax)  and more other format supported by pandoc.

Inspired by [DradisFS](https://github.com/NorthwaveSecurity/DradisFS) and based on the following libraries/project

* [dradis-api](https://github.com/NorthwaveSecurity/dradis-api) Python wrapper for the [Dradis API](https://dradisframework.com/support/guides/rest_api/)
* [pypandoc](https://github.com/NicklasTegner/pypandoc) wrapper for pandoc: markup file converting 
* [rich](https://github.com/Textualize/rich) for prettier output 🌈

**Table of contents**
- [DradisMD](#dradismd)
  - [Requirments](#requirments)
  - [Installation](#installation)
  - [Getting Started](#getting-started)
  - [Usage](#usage)
    - [--help](#--help)
    - [projects:](#projects)
    - [get](#get)
    - [update](#update)
    - [issues](#issues)
    - [add_issue](#add_issue)
    - [convert](#convert)
    - [rename](#rename)
  - [Changelog](#changelog)
  - [Markdown editor suggestion](#markdown-editor-suggestion)
  - [Missing features and known bugs](#missing-features-and-known-bugs)
    - [Nested nodes not supported](#nested-nodes-not-supported)
    - [Attachments not imported from Dradis](#attachments-not-imported-from-dradis)
  - [TODO:](#todo)

## Requirements

* **Python >= 3.10**  

To use the convertion features, [Pandoc](https://pandoc.org/) needs to be available in the $PATH.  
**Note**: DradisMD will detect if Pandoc is not installed and prompt to install it for you with pypandoc


## Installation

```
pip -r requirements.txt
```

## Getting Started

1. Find your **[API token](https://dradisframework.com/support/guides/rest_api/index.html#authentication)**
2. Set the instance URL and API token in config.ini

```
instance_url=hxxps://your-dradis-instance-url.com
api_token=your_api_token_here
```

3. List projects
```
python dradismd.py list
```

## Usage

DradisMD supports the followings action:
  * [--help](#help)                                           
  * [projects](#projects) 
  * [get](#get)
  * [update](#update)      
  * [issues](#issues)
  * [add_issue](#add_issue)
  * [convert](#convert)
  * [rename](#rename)


### --help
Show help message
```
python dradismd.py --help 
```

### projects:  
List projects with their IDs in last updated order.  
--head option to show only last X projects
```
python dradismd.py list [--head <number>]
```
### get
Retrieve a project from Dradis to local folder.  
Save to local folder if no destination folder is provided.
--format options to convert another format than textile
```
python dradismd.py get <project_id> [destination_folder] [--format <value>] 
```

**Example**:  
Import project with ID 17 to local folder and convert to markdown
```
python dradismd.py get 17 --format markdown
```

### update
⚠ **Disclaimer**: This action erases existing data on Dradis and replace it.   
If you are unsure what you are doing, make sure you have a backup of your Dradis project.

Export your local project file(s) to Dradis. Supports markdown and textile.  
If no source is provided, local folder is used.  
A single file can also be used
```
python dradismd.py update <project_id> [file|folder]           
```

**Examples**:  
Export project folder and all files inside
```
python dradismd.py update 167 "ProjectFolder"
```
Export a single  content block
```
python dradismd.py update 167 "ProjectFolder/Content Blocks/ContentBlock1.md"           
```
Note: The script expects the following folder structure (which is generated when using retrieving project with [get](#get):
```
📂 ProjectName
┣━━ 📂 Content Blocks
┃   ┣━━ 📄 ContentBlock1
┃   ┗━━ 📄 ContentBlock1     
┣━━ 📂 Issues
┃   ┗━━ 📄 Issue1
┣━━ 📂 Nodes
┃   ┗━━ 📂 Web application
┃       ┗━━ 📂 Evidences
┃           ┣━━ 📂 Issue1
┃           ┃   ┗━━📄 EvidenceXX
┃           ┗━━ 📂 Issue2
┃               ┗━━📄 EvidenceXX
┗━━ ⚙ document_properties.ini
```
The tool will not work properly if your local project has a different folder structure.

### issues

List issues from issue library.  
Search the issue library  for one of the keywords provided

```
python dradismd.py issues [keywords]
```

### add_issue

Add an issue to project folder from template or from issue library if --id is used
Create a new evidence too if --node  is provided

```
python dradismd.py add_issue <project_path> --id <id> or --title <title>
```



### convert
Convert a project file or all files in a folder to another format. Supported: markdown, textile
```
python dradismd.py convert <file|folder> <format>
```

### rename
Using the pattern defined in config.ini: Rename all attachments referenced in a project file and update the references
```
python dradismd.py rename <file>
```

## Changelog

**07/10/2022 - v0.2.0**
- Added add_issue and issues action
- Fixed rename

## Markdown editor suggestion

Below some of the markdown editor I would recommend trying

1. 🌟 Visual Code with the following extensions.  
   * [Markdown All in One](https://marketplace.visualstudio.com/items?itemName=yzhang.markdown-all-in-one)  
   * [Markdown Paste](https://marketplace.visualstudio.com/items?itemName=telesoho.vscode-markdown-paste-image)
   * [Markdown Shortcuts](https://marketplace.visualstudio.com/items?itemName=mdickin.markdown-shortcuts)
   * [Textile Preview](https://marketplace.visualstudio.com/items?itemName=michaelnewton.textile-preview)
2. [Joplin](https://joplinapp.org/)  
3. [ObsidianMD](https://obsidian.md/)  

Or literally any text editor such as VIM, Atom, Notepad++, ...

## Missing features and known bugs


### Nested nodes not supported

At the moment nested nodes are not supported (because I never used them).

### Attachments not imported from Dradis

The Dradis API doesn't allow to download attachments. 

## TODO:

- [X] Include interaction with [Issue Library](https://dradisframework.com/support/guides/rest_api/issuelibrary.html) to add new issue to project.
- [X] Fix bugs with the auto renaming feature
- [ ] Include more pandoc formats support (PDF, word, ...)
- [ ] VScode workspace with relevant markdown/textile extensions
