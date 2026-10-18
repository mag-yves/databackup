## Usages

    auth login
    auth logout
    filesystem list [-t TYPE] path
    filesystem info path
    filesystem size path
    filesystem create-folder parentPath name
    filesystem upload [-f STRATEGY] [-d STRATEGY] [-t] localPath... parentPath
    filesystem download [-f STRATEGY] [-d STRATEGY] path... localFolder
    filesystem rename path newName
    filesystem copy [-n NAME] sourcePath... targetParentPath
    filesystem move sourcePath... targetParentPath
    filesystem trash path...
    filesystem restore path...
    filesystem delete path...
    filesystem empty-trash
    sharing status path
    sharing invite [-u USER...] [-r ROLE] [-m MESSAGE] [-n] path
    sharing leave path
    sharing remove [-e EMAIL...] [-a] path
    sharing set-url [--role ROLE] [--password PASSWORD] [--expiration EXPIRATION] path
    sharing remove-url path
    invitation list
    invitation accept invitationUid
    invitation reject invitationUid
    album list
    album create name
    album update [-n NAME] [-c UID] albumPath
    album delete [-f] [-s] albumPath
    album photos [-d] albumPath
    album add-photo albumPath photoPath...
    album remove-photo albumPath photoPath...
    photo timeline [-d]
    photo upload [-c STRATEGY] localPath...
    photo download [-c STRATEGY] path... localFolder
    takeout run [-i INCLUDE...] localFolder

### Exemples

    # Se connecter (via navigateur web - interaction utilisateur obligatoire)
    ./proton-drive auth login

    # Lister les fichiers présents dans mon dossier source
    ./proton-drive filesystem list /my-files


## Options générales

    -h|--help: Show extended help for a command (example fs upload --help)
    -j|--json: Output in JSON format
    -v|--verbose: Enable verbose output

Any short names are supported (as long as they are unique):

    filesystem upload -> fs up
    sharing invite -> s inv

### Options filesystem upload

    -f, --file-conflict-strategy STRATEGY
        Conflict strategy applied to files. Values:
        * create-new-revision: Create a new revision of the
        existing file.
        * rename: Add a unique suffix to the name.
        * replace: Trash the remote file or folder and
        upload the local copy.
        * skip: Skip the conflicting file or folder.
    -d, --folder-conflict-strategy STRATEGY
        Conflict strategy applied to folders. Values:
        * merge: Merge folder contents.
        * rename: Add a unique suffix to the name.
        * replace: Trash the remote file or folder and
        upload the local copy.
        * skip: Skip the conflicting file or folder.
    -t, --skip-thumbnails    Skip generating thumbnails. (default: false)
