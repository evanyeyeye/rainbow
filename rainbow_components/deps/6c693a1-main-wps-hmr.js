webpackHotUpdaterainbow_components("main",{

/***/ "./src/lib/components/FilePicker.react.js":
/*!************************************************!*\
  !*** ./src/lib/components/FilePicker.react.js ***!
  \************************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "default", function() { return FilePicker; });
/* harmony import */ var chonky__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! chonky */ "./node_modules/chonky/dist/chonky.esm.js");
/* harmony import */ var chonky_icon_fontawesome__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! chonky-icon-fontawesome */ "./node_modules/chonky-icon-fontawesome/dist/chonky-icon-fontawesome.esm.js");
/* harmony import */ var prop_types__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! prop-types */ "./node_modules/prop-types/index.js");
/* harmony import */ var prop_types__WEBPACK_IMPORTED_MODULE_2___default = /*#__PURE__*/__webpack_require__.n(prop_types__WEBPACK_IMPORTED_MODULE_2__);
/* harmony import */ var react__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(/*! react */ "./node_modules/react/index.js");
/* harmony import */ var react__WEBPACK_IMPORTED_MODULE_3___default = /*#__PURE__*/__webpack_require__.n(react__WEBPACK_IMPORTED_MODULE_3__);
var _excluded = ["id", "setProps"];

function _slicedToArray(arr, i) { return _arrayWithHoles(arr) || _iterableToArrayLimit(arr, i) || _unsupportedIterableToArray(arr, i) || _nonIterableRest(); }

function _nonIterableRest() { throw new TypeError("Invalid attempt to destructure non-iterable instance.\nIn order to be iterable, non-array objects must have a [Symbol.iterator]() method."); }

function _unsupportedIterableToArray(o, minLen) { if (!o) return; if (typeof o === "string") return _arrayLikeToArray(o, minLen); var n = Object.prototype.toString.call(o).slice(8, -1); if (n === "Object" && o.constructor) n = o.constructor.name; if (n === "Map" || n === "Set") return Array.from(o); if (n === "Arguments" || /^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(n)) return _arrayLikeToArray(o, minLen); }

function _arrayLikeToArray(arr, len) { if (len == null || len > arr.length) len = arr.length; for (var i = 0, arr2 = new Array(len); i < len; i++) { arr2[i] = arr[i]; } return arr2; }

function _iterableToArrayLimit(arr, i) { var _i = arr == null ? null : typeof Symbol !== "undefined" && arr[Symbol.iterator] || arr["@@iterator"]; if (_i == null) return; var _arr = []; var _n = true; var _d = false; var _s, _e; try { for (_i = _i.call(arr); !(_n = (_s = _i.next()).done); _n = true) { _arr.push(_s.value); if (i && _arr.length === i) break; } } catch (err) { _d = true; _e = err; } finally { try { if (!_n && _i["return"] != null) _i["return"](); } finally { if (_d) throw _e; } } return _arr; }

function _arrayWithHoles(arr) { if (Array.isArray(arr)) return arr; }

function _objectWithoutProperties(source, excluded) { if (source == null) return {}; var target = _objectWithoutPropertiesLoose(source, excluded); var key, i; if (Object.getOwnPropertySymbols) { var sourceSymbolKeys = Object.getOwnPropertySymbols(source); for (i = 0; i < sourceSymbolKeys.length; i++) { key = sourceSymbolKeys[i]; if (excluded.indexOf(key) >= 0) continue; if (!Object.prototype.propertyIsEnumerable.call(source, key)) continue; target[key] = source[key]; } } return target; }

function _objectWithoutPropertiesLoose(source, excluded) { if (source == null) return {}; var target = {}; var sourceKeys = Object.keys(source); var key, i; for (i = 0; i < sourceKeys.length; i++) { key = sourceKeys[i]; if (excluded.indexOf(key) >= 0) continue; target[key] = source[key]; } return target; }






Object(chonky__WEBPACK_IMPORTED_MODULE_0__["setChonkyDefaults"])({
  iconComponent: chonky_icon_fontawesome__WEBPACK_IMPORTED_MODULE_1__["ChonkyIconFA"],
  disableDragAndDrop: true
});
function FilePicker(props) {
  var id = props.id,
      setProps = props.setProps,
      otherProps = _objectWithoutProperties(props, _excluded);

  var useFiles = function useFiles(currentFolderId) {
    return Object(react__WEBPACK_IMPORTED_MODULE_3__["useMemo"])(function () {
      var currentFolder = fileMap[currentFolderId];
      var files = currentFolder.childrenIds ? currentFolder.childrenIds.map(function (fileId) {
        var _fileMap$fileId;

        return (_fileMap$fileId = fileMap[fileId]) !== null && _fileMap$fileId !== void 0 ? _fileMap$fileId : null;
      }) : [];
      return files;
    }, [currentFolderId]);
  };

  var useFolderChain = function useFolderChain(currentFolderId) {
    return Object(react__WEBPACK_IMPORTED_MODULE_3__["useMemo"])(function () {
      var currentFolder = fileMap[currentFolderId];
      var folderChain = [currentFolder];
      var parentId = currentFolder.parentId;

      while (parentId) {
        var parentFile = fileMap[parentId];

        if (parentFile) {
          folderChain.unshift(parentFile);
          parentId = parentFile.parentId;
        } else {
          parentId = null;
        }
      }

      return folderChain;
    }, [currentFolderId]);
  };

  var useFileActionHandler = function useFileActionHandler(setCurrentFolderId) {
    return Object(react__WEBPACK_IMPORTED_MODULE_3__["useCallback"])(function (data) {
      if (data.id === chonky__WEBPACK_IMPORTED_MODULE_0__["ChonkyActions"].OpenFiles.id) {
        // if open action occurred on a folder, open it
        var _data$payload = data.payload,
            targetFile = _data$payload.targetFile,
            _files = _data$payload.files;
        var fileToOpen = targetFile !== null && targetFile !== void 0 ? targetFile : _files[0];

        if (fileToOpen && chonky__WEBPACK_IMPORTED_MODULE_0__["FileHelper"].isDirectory(fileToOpen)) {
          setCurrentFolderId(fileToOpen.id);
          return;
        }
      } else if (data.id === chonky__WEBPACK_IMPORTED_MODULE_0__["ChonkyActions"].ChangeSelection.id) {
        // get selected files
        var selectedFiles = data.payload.selection;
        selectedFiles = Array.from(selectedFiles);
        setProps({
          "selectedFiles": selectedFiles
        });
        console.log("selected:", selectedFiles);
        return;
      }
    }, [setCurrentFolderId]);
  };

  var fileMap = props.fileMap.fileMap || {};
  var rootFolderId = props.fileMap.rootFolderId;

  var _useState = Object(react__WEBPACK_IMPORTED_MODULE_3__["useState"])(rootFolderId),
      _useState2 = _slicedToArray(_useState, 2),
      currentFolderId = _useState2[0],
      setCurrentFolderId = _useState2[1];

  var files = useFiles(currentFolderId);
  var folderChain = useFolderChain(currentFolderId);
  var handleFileAction = useFileActionHandler(setCurrentFolderId);
  var actionsToDisable = [chonky__WEBPACK_IMPORTED_MODULE_0__["ChonkyActions"].OpenSelection.id, chonky__WEBPACK_IMPORTED_MODULE_0__["ChonkyActions"].SelectAllFiles.id, chonky__WEBPACK_IMPORTED_MODULE_0__["ChonkyActions"].ClearSelection.id];
  return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement(chonky__WEBPACK_IMPORTED_MODULE_0__["FileBrowser"], {
    files: files,
    folderChain: folderChain,
    onFileAction: handleFileAction,
    defaultFileViewActionId: chonky__WEBPACK_IMPORTED_MODULE_0__["ChonkyActions"].EnableListView.id,
    disableDefaultFileActions: actionsToDisable,
    disableSelection: true
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement(chonky__WEBPACK_IMPORTED_MODULE_0__["FileNavbar"], null), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement(chonky__WEBPACK_IMPORTED_MODULE_0__["FileToolbar"], null), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement(chonky__WEBPACK_IMPORTED_MODULE_0__["FileList"], null), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement(chonky__WEBPACK_IMPORTED_MODULE_0__["FileContextMenu"], null));
}
;
FilePicker.defaultProps = {
  selectedFiles: [],
  fileMap: {}
};
FilePicker.propTypes = {
  /**
   * The ID used to identify this component in Dash callbacks.
   */
  id: prop_types__WEBPACK_IMPORTED_MODULE_2___default.a.string,

  /**
   * Selected files.
   */
  selectedFiles: prop_types__WEBPACK_IMPORTED_MODULE_2___default.a.array,

  /**
   * JSON-style dictionary containing file tree.
   */
  fileMap: prop_types__WEBPACK_IMPORTED_MODULE_2___default.a.object,

  /**
   * Dash-assigned callback that should be called to report property changes
   * to Dash, to make them available for callbacks.
   */
  setProps: prop_types__WEBPACK_IMPORTED_MODULE_2___default.a.func
};

/***/ })

})
//# sourceMappingURL=6c693a1-main-wps-hmr.js.map
//# sourceMappingURL=data:application/json;charset=utf-8;base64,eyJ2ZXJzaW9uIjozLCJzb3VyY2VzIjpbXSwibmFtZXMiOltdLCJtYXBwaW5ncyI6IiIsImZpbGUiOiI2YzY5M2ExLW1haW4td3BzLWhtci5qcyIsInNvdXJjZVJvb3QiOiIifQ==