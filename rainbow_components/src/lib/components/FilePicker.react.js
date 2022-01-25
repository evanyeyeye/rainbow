import {
    ChonkyActions,
    FileBrowser,
    FileContextMenu,
    FileHelper,
    FileList,
    FileNavbar,
    FileToolbar,
    setChonkyDefaults,
} from 'chonky';
import { ChonkyIconFA } from 'chonky-icon-fontawesome';
import PropTypes from 'prop-types';
import React from 'react';
import { useState, useEffect, useMemo, useCallback } from 'react';
import "./FilePicker.css";

setChonkyDefaults({
  iconComponent: ChonkyIconFA,
  disableDragAndDrop: true
});

export default function FilePicker(props) {
  // get data
  const {
    id,
    multiple_selection_allowed : multipleSelectionAllowed,
    ...otherProps
  } = props;

  const file_map = props.file_map ?? { rootFolderId : "none", fileMap : {} };
  const fileMap = file_map.fileMap;

  // get the setProps function, which is used to communicate
  // changes in the props back to Dash
  // setProps will not be defined unless this component is
  // running in Dash, so use a dummy function in standalone mode
  let setProps;
  if ( props["setProps"] ) {
    setProps = props["setProps"]
  }
  else {
    setProps = () => {}
  }

  const useFiles = (currentFolderId, fileMask) => {
    return useMemo(() => {
      const currentFolder = fileMap[currentFolderId];
      const files = [];
      currentFolder.childrenIds.forEach(id => {
        const filename = fileMap[id];
        if (filename) {
          if ( ( fileMask && filename["name"].includes(fileMask) ) ||
               ( !fileMask ) ) {
            files.push(filename);
          }
        }
      });
      // const files = currentFolder.childrenIds
      //     ? currentFolder.childrenIds.map((fileId) => fileMap[fileId] ?? null)
      //     : [];
      return files;
    }, [currentFolderId, file_map, fileMask]);
  };

  const useFolderChain = (currentFolderId) => {
    return useMemo(() => {
      const currentFolder = fileMap[currentFolderId];
      const folderChain = [currentFolder];

      let parentId = currentFolder.parentId;
      while (parentId) {
        const parentFile = fileMap[parentId];
        if (parentFile) {
            folderChain.unshift(parentFile);
            parentId = parentFile.parentId;
        } else {
            parentId = null;
        }
      }

      return folderChain;
    }, [currentFolderId, file_map]);
  };

  const useFileActionHandler = (setCurrentFolderId) => {
    return useCallback((data) => {
      if (data.id === ChonkyActions.OpenFiles.id) {
        const { targetFile, files } = data.payload;
        const fileToOpen = targetFile ?? files[0];
        if (fileToOpen && FileHelper.isDirectory(fileToOpen)) {
            setCurrentFolderId(fileToOpen.id);
            setProps({"selected_files" : []});
        }
      }
      else if ( multipleSelectionAllowed && data.id === ChonkyActions.ChangeSelection.id ) {
        const { selection } = data.payload;
        const selectedFiles = Array.from(selection);
        //console.log("multiple selection", selectedFiles);
        setProps({"selected_files" : selectedFiles})
      }
      else if ( !multipleSelectionAllowed && data.id === ChonkyActions.MouseClickFile.id ) {
        const clickType = data.payload.clickType;
        if ( clickType == "single" ) {
          const currentId = data.payload.file.id || "none";
          const currentIdArray = [ currentId ];         
          //console.log("single selection:", currentIdArray);
          setProps({"selected_files" : currentIdArray});
        }
      }
    },
    [setCurrentFolderId]);
  }

  const [currentFolderId, setCurrentFolderId] = useState(file_map.rootFolderId);
  const [fileMask, setFileMask] = useState();
  const handleChange = (e) => {
    setFileMask(e.target.value);
  };

  const files = useFiles(currentFolderId, fileMask);
  useEffect(() => {
    //console.log("setting root folder id to", currentFolderId);
    setProps({ "root_folder_id" : currentFolderId });
  }, [currentFolderId]);
  const folderChain = useFolderChain(currentFolderId);
  const handleFileAction = useFileActionHandler(setCurrentFolderId);


  const actionsToDisable = [ ChonkyActions.OpenSelection.id ]
  if (!multipleSelectionAllowed) {
    actionsToDisable.push(ChonkyActions.SelectAllFiles.id);
    actionsToDisable.push(ChonkyActions.ClearSelection.id);
  }

  return (
    <div className="FilePicker">
      <input type="text" className="SearchBox" onChange={handleChange} placeholder="search"/>
      <FileBrowser
        files={files}
        folderChain={folderChain}
        onFileAction={handleFileAction}
        defaultFileViewActionId={ChonkyActions.EnableListView.id}
        disableDefaultFileActions={actionsToDisable}
        disableSelection={!multipleSelectionAllowed}
      >
        <FileNavbar />
        <FileToolbar />
        <FileList />
      </FileBrowser>
    </div>
  );
};

FilePicker.defaultProps = {
    selected_files : [],
    file_map : {},
    root_folder_id : '',
    multiple_selection_allowed : true,
};

FilePicker.propTypes = {
    /**
     * The ID used to identify this component in Dash callbacks.
     */
    id: PropTypes.string,

    /**
     * Whether we are allowed to select multiple files
     */
    multiple_selection_allowed: PropTypes.bool,

    /**
     * Selected files.
     */
    selected_files: PropTypes.array,

    /**
     * The id of the root folder.
     */
    root_folder_id: PropTypes.string,

    /**
     * JSON-style dictionary containing file tree.
     */
    file_map: PropTypes.object,

    /**
     * Dash-assigned callback that should be called to report property changes
     * to Dash, to make them available for callbacks.
     */
    setProps: PropTypes.func
};
