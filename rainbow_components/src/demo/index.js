import React from 'react';
import ReactDOM from 'react-dom';
import FilePicker from '../lib/components/FilePicker.react.js'
import fileMap from './filemap.json';


ReactDOM.render(
	<div style={{"height":500}}>
	  test
	  <FilePicker file_map={fileMap} multiple_selection_allowed={true}/>
	</div>,
	document.getElementById('root')
);
