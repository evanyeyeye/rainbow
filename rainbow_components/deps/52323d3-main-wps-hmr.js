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

/***/ "./src/demo/index.js":
/*!***************************!*\
  !*** ./src/demo/index.js ***!
  \***************************/
/*! no exports provided */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony import */ var react__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! react */ "./node_modules/react/index.js");
/* harmony import */ var react__WEBPACK_IMPORTED_MODULE_0___default = /*#__PURE__*/__webpack_require__.n(react__WEBPACK_IMPORTED_MODULE_0__);
/* harmony import */ var react_dom__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! react-dom */ "./node_modules/react-dom/index.js");
/* harmony import */ var react_dom__WEBPACK_IMPORTED_MODULE_1___default = /*#__PURE__*/__webpack_require__.n(react_dom__WEBPACK_IMPORTED_MODULE_1__);
/* harmony import */ var _lib_components_FilePicker_react_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! ../lib/components/FilePicker.react.js */ "./src/lib/components/FilePicker.react.js");
/* harmony import */ var _filemap_json__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(/*! ./filemap.json */ "./src/demo/filemap.json");
var _filemap_json__WEBPACK_IMPORTED_MODULE_3___namespace = /*#__PURE__*/__webpack_require__.t(/*! ./filemap.json */ "./src/demo/filemap.json", 1);




react_dom__WEBPACK_IMPORTED_MODULE_1___default.a.render( /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_0___default.a.createElement("div", {
  style: {
    "height": 500,
    "width": 1000
  }
}, "test", /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_0___default.a.createElement(_lib_components_FilePicker_react_js__WEBPACK_IMPORTED_MODULE_2__["default"], {
  file_map: _filemap_json__WEBPACK_IMPORTED_MODULE_3__,
  multiple_selection_allowed: true
})), document.getElementById('root'));

/***/ })

})
//# sourceMappingURL=52323d3-main-wps-hmr.js.map
//# sourceMappingURL=data:application/json;charset=utf-8;base64,eyJ2ZXJzaW9uIjozLCJzb3VyY2VzIjpbXSwibmFtZXMiOltdLCJtYXBwaW5ncyI6IiIsImZpbGUiOiI1MjMyM2QzLW1haW4td3BzLWhtci5qcyIsInNvdXJjZVJvb3QiOiIifQ==