webpackHotUpdaterainbow_components("main",{

/***/ "./node_modules/react-intl/lib/index.js":
/*!**********************************************!*\
  !*** ./node_modules/react-intl/lib/index.js ***!
  \**********************************************/
/*! exports provided: FormattedDateTimeRange, FormattedMessage, FormattedPlural, FormattedRelativeTime, IntlContext, IntlProvider, RawIntlProvider, createIntl, injectIntl, useIntl, createIntlCache, UnsupportedFormatterError, InvalidConfigError, MissingDataError, MessageFormatError, MissingTranslationError, ReactIntlErrorCode, ReactIntlError, defineMessages, defineMessage, FormattedDate, FormattedTime, FormattedNumber, FormattedList, FormattedDisplayName, FormattedDateParts, FormattedTimeParts, FormattedNumberParts, FormattedListParts */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "defineMessages", function() { return defineMessages; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "defineMessage", function() { return defineMessage; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "FormattedDate", function() { return FormattedDate; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "FormattedTime", function() { return FormattedTime; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "FormattedNumber", function() { return FormattedNumber; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "FormattedList", function() { return FormattedList; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "FormattedDisplayName", function() { return FormattedDisplayName; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "FormattedDateParts", function() { return FormattedDateParts; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "FormattedTimeParts", function() { return FormattedTimeParts; });
/* harmony import */ var _src_components_createFormattedComponent__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! ./src/components/createFormattedComponent */ "./node_modules/react-intl/lib/src/components/createFormattedComponent.js");
/* harmony import */ var _src_components_injectIntl__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! ./src/components/injectIntl */ "./node_modules/react-intl/lib/src/components/injectIntl.js");
/* harmony reexport (safe) */ __webpack_require__.d(__webpack_exports__, "IntlContext", function() { return _src_components_injectIntl__WEBPACK_IMPORTED_MODULE_1__["Context"]; });

/* harmony reexport (safe) */ __webpack_require__.d(__webpack_exports__, "RawIntlProvider", function() { return _src_components_injectIntl__WEBPACK_IMPORTED_MODULE_1__["Provider"]; });

/* harmony reexport (safe) */ __webpack_require__.d(__webpack_exports__, "injectIntl", function() { return _src_components_injectIntl__WEBPACK_IMPORTED_MODULE_1__["default"]; });

/* harmony import */ var _src_components_useIntl__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! ./src/components/useIntl */ "./node_modules/react-intl/lib/src/components/useIntl.js");
/* harmony reexport (safe) */ __webpack_require__.d(__webpack_exports__, "useIntl", function() { return _src_components_useIntl__WEBPACK_IMPORTED_MODULE_2__["default"]; });

/* harmony import */ var _src_components_provider__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(/*! ./src/components/provider */ "./node_modules/react-intl/lib/src/components/provider.js");
/* harmony reexport (safe) */ __webpack_require__.d(__webpack_exports__, "IntlProvider", function() { return _src_components_provider__WEBPACK_IMPORTED_MODULE_3__["default"]; });

/* harmony reexport (safe) */ __webpack_require__.d(__webpack_exports__, "createIntl", function() { return _src_components_provider__WEBPACK_IMPORTED_MODULE_3__["createIntl"]; });

/* harmony import */ var _src_components_relative__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(/*! ./src/components/relative */ "./node_modules/react-intl/lib/src/components/relative.js");
/* harmony reexport (safe) */ __webpack_require__.d(__webpack_exports__, "FormattedRelativeTime", function() { return _src_components_relative__WEBPACK_IMPORTED_MODULE_4__["default"]; });

/* harmony import */ var _src_components_plural__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(/*! ./src/components/plural */ "./node_modules/react-intl/lib/src/components/plural.js");
/* harmony reexport (safe) */ __webpack_require__.d(__webpack_exports__, "FormattedPlural", function() { return _src_components_plural__WEBPACK_IMPORTED_MODULE_5__["default"]; });

/* harmony import */ var _src_components_message__WEBPACK_IMPORTED_MODULE_6__ = __webpack_require__(/*! ./src/components/message */ "./node_modules/react-intl/lib/src/components/message.js");
/* harmony reexport (safe) */ __webpack_require__.d(__webpack_exports__, "FormattedMessage", function() { return _src_components_message__WEBPACK_IMPORTED_MODULE_6__["default"]; });

/* harmony import */ var _src_components_dateTimeRange__WEBPACK_IMPORTED_MODULE_7__ = __webpack_require__(/*! ./src/components/dateTimeRange */ "./node_modules/react-intl/lib/src/components/dateTimeRange.js");
/* harmony reexport (safe) */ __webpack_require__.d(__webpack_exports__, "FormattedDateTimeRange", function() { return _src_components_dateTimeRange__WEBPACK_IMPORTED_MODULE_7__["default"]; });

/* harmony import */ var _formatjs_intl__WEBPACK_IMPORTED_MODULE_8__ = __webpack_require__(/*! @formatjs/intl */ "./node_modules/@formatjs/intl/lib/index.js");
/* harmony reexport (safe) */ __webpack_require__.d(__webpack_exports__, "createIntlCache", function() { return _formatjs_intl__WEBPACK_IMPORTED_MODULE_8__["createIntlCache"]; });

/* harmony reexport (safe) */ __webpack_require__.d(__webpack_exports__, "UnsupportedFormatterError", function() { return _formatjs_intl__WEBPACK_IMPORTED_MODULE_8__["UnsupportedFormatterError"]; });

/* harmony reexport (safe) */ __webpack_require__.d(__webpack_exports__, "InvalidConfigError", function() { return _formatjs_intl__WEBPACK_IMPORTED_MODULE_8__["InvalidConfigError"]; });

/* harmony reexport (safe) */ __webpack_require__.d(__webpack_exports__, "MissingDataError", function() { return _formatjs_intl__WEBPACK_IMPORTED_MODULE_8__["MissingDataError"]; });

/* harmony reexport (safe) */ __webpack_require__.d(__webpack_exports__, "MessageFormatError", function() { return _formatjs_intl__WEBPACK_IMPORTED_MODULE_8__["MessageFormatError"]; });

/* harmony reexport (safe) */ __webpack_require__.d(__webpack_exports__, "MissingTranslationError", function() { return _formatjs_intl__WEBPACK_IMPORTED_MODULE_8__["MissingTranslationError"]; });

/* harmony reexport (safe) */ __webpack_require__.d(__webpack_exports__, "ReactIntlErrorCode", function() { return _formatjs_intl__WEBPACK_IMPORTED_MODULE_8__["IntlErrorCode"]; });

/* harmony reexport (safe) */ __webpack_require__.d(__webpack_exports__, "ReactIntlError", function() { return _formatjs_intl__WEBPACK_IMPORTED_MODULE_8__["IntlError"]; });

/* harmony reexport (safe) */ __webpack_require__.d(__webpack_exports__, "FormattedNumberParts", function() { return _src_components_createFormattedComponent__WEBPACK_IMPORTED_MODULE_0__["FormattedNumberParts"]; });

/* harmony reexport (safe) */ __webpack_require__.d(__webpack_exports__, "FormattedListParts", function() { return _src_components_createFormattedComponent__WEBPACK_IMPORTED_MODULE_0__["FormattedListParts"]; });











function defineMessages(msgs) {
    return msgs;
}
function defineMessage(msg) {
    return msg;
}
// IMPORTANT: Explicit here to prevent api-extractor from outputing `import('./src/types').CustomFormatConfig`
var FormattedDate = Object(_src_components_createFormattedComponent__WEBPACK_IMPORTED_MODULE_0__["createFormattedComponent"])('formatDate');
var FormattedTime = Object(_src_components_createFormattedComponent__WEBPACK_IMPORTED_MODULE_0__["createFormattedComponent"])('formatTime');
// @ts-ignore issue w/ TS Intl types
var FormattedNumber = Object(_src_components_createFormattedComponent__WEBPACK_IMPORTED_MODULE_0__["createFormattedComponent"])('formatNumber');
var FormattedList = Object(_src_components_createFormattedComponent__WEBPACK_IMPORTED_MODULE_0__["createFormattedComponent"])('formatList');
var FormattedDisplayName = Object(_src_components_createFormattedComponent__WEBPACK_IMPORTED_MODULE_0__["createFormattedComponent"])('formatDisplayName');
var FormattedDateParts = Object(_src_components_createFormattedComponent__WEBPACK_IMPORTED_MODULE_0__["createFormattedDateTimePartsComponent"])('formatDate');
var FormattedTimeParts = Object(_src_components_createFormattedComponent__WEBPACK_IMPORTED_MODULE_0__["createFormattedDateTimePartsComponent"])('formatTime');



/***/ }),

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
var _excluded = ["id", "multiple_selection_allowed", "id_to_refresh", "setProps"];

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
      multipleSelectionAllowed = props.multiple_selection_allowed,
      idToRefresh = props.id_to_refresh,
      setProps = props.setProps,
      otherProps = _objectWithoutProperties(props, _excluded);

  var useFolderChain = function useFolderChain(currentFolderId) {
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
  };

  var useFileActionHandler = function useFileActionHandler(setCurrentFolderId) {
    (function (data) {
      // when a file is clicked on...
      if (data.id === chonky__WEBPACK_IMPORTED_MODULE_0__["ChonkyActions"].MouseClickFile.id || data.id === chonky__WEBPACK_IMPORTED_MODULE_0__["ChonkyActions"].KeyboardClickFile) {
        // if the component is in single selection mode,
        // then update the current selection
        var currentFile = data.payload.file.id || "none";
        var currentFileArray = [currentFile];
        setProps({
          "selected_files": currentFileArray
        });
        console.log("current single selection:", currentFile); // set this file to be re-explored on the backend

        if (currentFile != "none") {
          setProps({
            "id_to_refresh": data.payload.file.id
          });
        }
      } // if the user opens a folder, change the root folder internally


      if (data.id === chonky__WEBPACK_IMPORTED_MODULE_0__["ChonkyActions"].OpenFiles.id) {
        var _data$payload = data.payload,
            targetFile = _data$payload.targetFile,
            _files = _data$payload.files;
        var fileToOpen = targetFile !== null && targetFile !== void 0 ? targetFile : _files[0];

        if (fileToOpen && chonky__WEBPACK_IMPORTED_MODULE_0__["FileHelper"].isDirectory(fileToOpen)) {
          setCurrentFolderId(fileToOpen.id); //setProps({ "id_to_refresh" : fileToOpen.id });
        }
      } // if we are in multiple selection mode and the selection changes,
      // then update the current selection
      else if (multipleSelectionAllowed && data.id === chonky__WEBPACK_IMPORTED_MODULE_0__["ChonkyActions"].ChangeSelection.id) {
        var selectedFiles = data.payload.selection;
        selectedFiles = Array.from(selectedFiles);
        setProps({
          "selectedFiles": selectedFiles
        });
        console.log("current multiple selection:", selectedFiles);
      }
    });
  };

  var fileMap = props.file_map.fileMap || {}; //console.log("fileMap", Object.keys(fileMap).length);

  var rootFolderId = props.file_map.rootFolderId;
  console.log("a", rootFolderId);

  var _useState = Object(react__WEBPACK_IMPORTED_MODULE_3__["useState"])(rootFolderId),
      _useState2 = _slicedToArray(_useState, 2),
      currentFolderId = _useState2[0],
      setCurrentFolderId = _useState2[1];

  var currentFolder = fileMap[currentFolderId];
  var files = currentFolder.childrenIds ? currentFolder.childrenIds.map(function (fileId) {
    var _fileMap$fileId;

    return (_fileMap$fileId = fileMap[fileId]) !== null && _fileMap$fileId !== void 0 ? _fileMap$fileId : null;
  }) : []; //console.log("files", files);

  var folderChain = useFolderChain(currentFolderId);
  var handleFileAction = useFileActionHandler(setCurrentFolderId);
  var actionsToDisable = [chonky__WEBPACK_IMPORTED_MODULE_0__["ChonkyActions"].OpenSelection.id];

  if (!multipleSelectionAllowed) {
    actionsToDisable.push(chonky__WEBPACK_IMPORTED_MODULE_0__["ChonkyActions"].SelectAllFiles.id);
    actionsToDisable.push(chonky__WEBPACK_IMPORTED_MODULE_0__["ChonkyActions"].ClearSelection.id);
  }

  return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement(chonky__WEBPACK_IMPORTED_MODULE_0__["FileBrowser"], {
    files: files,
    folderChain: folderChain,
    onFileAction: handleFileAction,
    defaultFileViewActionId: chonky__WEBPACK_IMPORTED_MODULE_0__["ChonkyActions"].EnableListView.id,
    disableDefaultFileActions: actionsToDisable,
    disableSelection: !multipleSelectionAllowed
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement(chonky__WEBPACK_IMPORTED_MODULE_0__["FileNavbar"], null), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement(chonky__WEBPACK_IMPORTED_MODULE_0__["FileToolbar"], null), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement(chonky__WEBPACK_IMPORTED_MODULE_0__["FileList"], null));
}
;
FilePicker.defaultProps = {
  selected_files: [],
  file_map: {},
  id_to_refresh: '',
  multiple_selection_allowed: true
};
FilePicker.propTypes = {
  /**
   * The ID used to identify this component in Dash callbacks.
   */
  id: prop_types__WEBPACK_IMPORTED_MODULE_2___default.a.string,

  /**
   * Whether we are allowed to select multiple files
   */
  multiple_selection_allowed: prop_types__WEBPACK_IMPORTED_MODULE_2___default.a.bool,

  /**
   * Selected files.
   */
  selected_files: prop_types__WEBPACK_IMPORTED_MODULE_2___default.a.array,

  /**
   * When this id changes, Dash should explore the given id.
   */
  id_to_refresh: prop_types__WEBPACK_IMPORTED_MODULE_2___default.a.string,

  /**
   * JSON-style dictionary containing file tree.
   */
  file_map: prop_types__WEBPACK_IMPORTED_MODULE_2___default.a.object,

  /**
   * Dash-assigned callback that should be called to report property changes
   * to Dash, to make them available for callbacks.
   */
  setProps: prop_types__WEBPACK_IMPORTED_MODULE_2___default.a.func
};

/***/ })

})
//# sourceMappingURL=fd16207-main-wps-hmr.js.map
//# sourceMappingURL=data:application/json;charset=utf-8;base64,eyJ2ZXJzaW9uIjozLCJzb3VyY2VzIjpbXSwibmFtZXMiOltdLCJtYXBwaW5ncyI6IiIsImZpbGUiOiJmZDE2MjA3LW1haW4td3BzLWhtci5qcyIsInNvdXJjZVJvb3QiOiIifQ==