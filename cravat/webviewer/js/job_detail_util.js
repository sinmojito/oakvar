function getEl (tag) {
	var div = document.createElement(tag);
	return div;
}

function getTn (text) {
	return document.createTextNode(text);
}

function addEl (parent, child) {
	parent.appendChild(child);
	return parent;
}

function getTrimmedTn (text) {
	var textLengthCutoff = 10;
	var span = getEl('span');
	var tn = getTn(text);
	if (text.length > textLengthCutoff) {
		span.title = text;
		text = text.substring(0, textLengthCutoff) + '...';
		tn.textContent = text;
	}
	addEl(span, tn);
	return span;
}

function getExclamationTd (flag) {
	var td = document.createElement('td');
	td.style.width = 50;
	if (flag == true) {
		var img = new Image();
		img.src = 'images/exclamation.png';
		img.width = 14;
		img.height = 14;
		td.appendChild(img);
	}
	return td;
}

function getTextTd (text) {
	var td = document.createElement('td');
	td.style.width = 150;
	td.appendChild(document.createTextNode(text));
	return td;
}

//Function to convert seconds to HH:MM:SS
function toHHMMSS (sec_num) {
    var hours   = Math.floor(sec_num / 3600);
    var minutes = Math.floor((sec_num - (hours * 3600)) / 60);
    var seconds = sec_num - (hours * 3600) - (minutes * 60);

    if (hours   < 10) {hours   = "0"+hours;}
    if (minutes < 10) {minutes = "0"+minutes;}
    if (seconds < 10) {seconds = "0"+seconds;}
    
    return hours+':'+minutes+':'+seconds;
}

function getDetailWidgetDivs (tabName, widgetName, title) {
	var div = document.createElement('fieldset');
	div.id = 'detailwidget_' + tabName + '_' + widgetName;
	div.className = 'detailwidget';
	div.clientWidth = widgetGenerators[widgetName][tabName]['width'];
	div.clientHeight = widgetGenerators[widgetName][tabName]['height'];
	div.style.width = widgetGenerators[widgetName][tabName]['width'] + 'px';
	div.style.height = widgetGenerators[widgetName][tabName]['height'] + 'px';
	div.setAttribute('widgetkey', widgetName);
	
	// Header
	var header = getEl('div');
	header.className = 'detailwidgetheader';
	addEl(div, header);
	
	// Title
	var titleDiv = getEl('legend');
	titleDiv.className = 'detailwidgettitle';
	titleDiv.style.cursor = 'move';
	addEl(div, addEl(titleDiv, getTn(title)));
	
	// Div for pin and x icons
	var iconDiv = getEl('div');
	iconDiv.className = 'detailwidgeticondiv';
	addEl(header, iconDiv);

	// Pin button
	var pinButton = getEl('img');
	pinButton.src = '/images/pin.png';
	pinButton.className = 'detailwidgetpinbutton';
	pinButton.classList.add('unpinned');
	pinButton.setAttribute('widgetname', widgetName);
	pinButton.addEventListener('click', function (evt) {
		onClickWidgetPinButton(evt, tabName);
	});
	addEl(iconDiv, pinButton);

	// Close button
	var closeButton = getEl('img');
	closeButton.src = 'images/close-button.png';
	closeButton.className = 'closebutton';
	//closeButton.className = 'detailwidgetclosebutton';
	closeButton.setAttribute('widgetname', widgetName);
	closeButton.addEventListener('click', function (evt) {
		onClickWidgetCloseButton(tabName, evt);
	});
	addEl(iconDiv, closeButton);
	
	var hr = getEl('hr');
	addEl(div, hr);
	
	// Content div
	var detailContentDiv = getEl('div');
	detailContentDiv.id = 'widgetcontentdiv_' + widgetName + '_' + tabName;
	detailContentDiv.className = 'detailcontentdiv';
	detailContentDiv.style.height = 'calc(100% - 37px)';
	//detailContentDiv.style.height = '100%';
	addEl(div, detailContentDiv);
	
	return [div, detailContentDiv];
}

function addSpinner(parentDiv, scaleFactor, minDim, spinnerDivId){
	var parentRect = parentDiv.getBoundingClientRect();
	var scaleDim = Math.floor(scaleFactor * Math.min(parentRect.width, parentRect.height));
	var spinnerDim = Math.max(scaleDim, minDim);
	var spinnerDiv = getEl('div');
	spinnerDiv.id = spinnerDivId;
	spinnerDiv.style.position = 'absolute';
	spinnerDiv.style.textAlign = 'center';
	var spinnerImg = getEl('img');
	spinnerImg.src = "images/bigSpinner.gif";
	spinnerImg.style.width = spinnerDim + 'px';
	spinnerImg.style.height = spinnerDim + 'px';
	addEl(spinnerDiv, spinnerImg);
	addEl(parentDiv, spinnerDiv);
	var spinnerRect = spinnerDiv.getBoundingClientRect();
	
	spinnerDiv.style.top = parentRect.top + parentRect.height/2 - spinnerRect.height/2;
	spinnerDiv.style.left = parentRect.left + parentRect.width/2 - spinnerRect.width/2;
	return spinnerDiv;
}

function addSpinnerById(parentDivId, scaleFactor, minDim, spinnerDivId){
	var parentDiv = document.getElementById(parentDivId);
	var spinnerDiv = addSpinner(parentDiv, scaleFactor, minDim, spinnerDivId);
	return spinnerDiv;
}

function saveFilterSetting (name) {
	var saveData = {};
	saveData['filterSet'] = filterSet;
	var saveDataStr = JSON.stringify(saveData);
	$.get('rest/service/savefiltersetting', {'dbpath': dbPath, name: name, 'savedata': saveDataStr}).done(function (response) {
		writeLogDiv('Filter setting has been saved.');
    });
}

function saveLayoutSetting (name, callback) {
	saveTableSetting(name);
	saveWidgetSetting(name);
	lastUsedLayoutName = name;
	if (callback != null) {
		callback();
	}
}

function saveFilterSettingAs () {
	$.get('rest/service/getlayoutsavenames', {'dbpath': dbPath}).done(function (response) {
		var names = '' + JSON.parse(response.replace(/'/g, '"'));
		var msg = 'Please enter layout name to save.';
		if (names != '') {
			msg = msg + ' Saved layout names are ' + names;
		}
		var name = prompt(msg, lastUsedLayoutName);
		if (name != null) {
			saveFilterSetting(name);
		}
	});
}
function saveLayoutSettingAs () {
	$.get('rest/service/getlayoutsavenames', {'dbpath': dbPath}).done(function (response) {
		var names = '' + JSON.parse(response.replace(/'/g, '"'));
		var msg = 'Please enter layout name to save.';
		if (names != '') {
			msg = msg + ' Saved layout names are ' + names;
		}
		var name = prompt(msg, lastUsedLayoutName);
		if (name != null) {
			saveTableSetting(name);
			saveWidgetSetting(name);
		}
	});
}

function saveWidgetSetting (name) {
	var saveData = {};
	saveData['widgetSettings'] = {};
	var widgets = {};
	var detailContainerDiv = document.getElementById('detailcontainerdiv_variant');
	if (detailContainerDiv != null) {
		saveData['widgetSettings']['variant'] = [];
		widgets = $(detailContainerDiv).packery('getItemElements');
		for (var i = 0; i < widgets.length; i++) {
			var widget = widgets[i];
			saveData['widgetSettings']['variant'].push(
					{'id': widget.id,
					'widgetkey': widget.getAttribute('widgetkey'),
					'top': widget.style.top, 
					'left': widget.style.left, 
					'width': widget.style.width, 
					'height': widget.style.height});
		};
	}
	var detailContainerDiv = document.getElementById('detailcontainerdiv_gene');
	if (detailContainerDiv != null) {
		saveData['widgetSettings']['gene'] = [];
		widgets = $(detailContainerDiv).packery('getItemElements');
		for (var i = 0; i < widgets.length; i++) {
			var widget = widgets[i];
			saveData['widgetSettings']['gene'].push(
					{'id': widget.id,
					'widgetkey': widget.getAttribute('widgetkey'),
					'top': widget.style.top, 
					'left': widget.style.left, 
					'width': widget.style.width, 
					'height': widget.style.height});
		};
	}
	var saveDataStr = JSON.stringify(saveData);
	$.ajax({
		url: 'rest/service/savewidgetsetting', 
		type: 'get',
		async: false,
		data: {'dbpath': dbPath, name: name, 'savedata': saveDataStr},
		success: function (response) {
			writeLogDiv('Widget setting has been saved.');
		}
    });
}

function saveTableSetting (name) {
	var saveData = {};
	saveData['tableSettings'] = {};
	if ($grids['variant'] != undefined) {
		var colGroupModel = $grids['variant'].pqGrid('option', 'colModel');
		var data = [];
		for (var i = 0; i < colGroupModel.length; i++) {
			var colGroup = colGroupModel[i];
			var group = {};
			group = {'title': colGroup.title, 'cols': []};
			var cols = colGroup.colModel;
			for (var j = 0; j < cols.length; j++) {
				var col = cols[j];
				group.cols.push({'col': col.col, 'dataIndx': col.dataIndx, 'width': col.width});
			}
			data.push(group);
		}
		saveData['tableSettings']['variant'] = data;
	}
	if ($grids['gene'] != undefined) {
		var colGroupModel = $grids['gene'].pqGrid('option', 'colModel');
		var data = [];
		for (var i = 0; i < colGroupModel.length; i++) {
			var colGroup = colGroupModel[i];
			var group = {};
			group = {'title': colGroup.title, 'cols': []};
			var cols = colGroup.colModel;
			for (var j = 0; j < cols.length; j++) {
				var col = cols[j];
				group.cols.push({'col': col.col, 'dataIndx': col.dataIndx, 'width': col.width});
			}
			data.push(group);
		}
		saveData['tableSettings']['gene'] = data;
	}
	var saveDataStr = JSON.stringify(saveData);
	console.log(saveData);
	$.ajax({
		url: 'rest/service/savetablesetting', 
		type: 'get',
		data: {'dbpath': dbPath, name: name, 'savedata': saveDataStr}, 
		async: false,
		success: function (response) {
			writeLogDiv('Table setting has been saved.');
		}
    });
}

function areSameFilters (filter1, filter2) {
	var sameFilter = true;
	for (var i = 0; i < filter1.length; i++) {
		var el1 = filter1[i];
		var sameEl = false;
		for (var j = 0; j < filter2.length; j++) {
			var el2 = filter2[j];
			if (el1[0].col == el2[0].col && el1[1] == el2[1] && el1[2] == el2[2] && el1[3] == el2[3]) {
				sameEl = true;
				break;
			}
		}
		if (sameEl == false) {
			sameFilter = false;
			break;
		}
	}
	for (var i = 0; i < filter2.length; i++) {
		var el1 = filter2[i];
		var sameEl = false;
		for (var j = 0; j < filter1.length; j++) {
			var el2 = filter1[j];
			if (el1[0].col == el2[0].col && el1[1] == el2[1] && el1[2] == el2[2] && el1[3] == el2[3]) {
				sameEl = true;
				break;
			}
		}
		if (sameEl == false) {
			sameFilter = false;
			break;
		}
	}
	return sameFilter;
}

function showTab (tabName) {
	$('.tabhead.show').removeClass('show').addClass('hide');
	$('#tabhead_' + tabName).removeClass('hide').addClass('show');
	$('.tabcontent.show').removeClass('show').addClass('hide');
	$('#tab_' + tabName).removeClass('hide').addClass('show');
}

function loadFilterSetting (name, callback) {
	$.get('rest/service/loadfiltersetting', {'dbpath': dbPath, 'name': name}).done(function (response) {
		writeLogDiv('Filter setting loaded');
		response = response.replace(/'/g, '"');
		var data = JSON.parse(response);
		var loadedFilterSet = data['filterSet'];
		filterSet = loadedFilterSet;
		showFilterSet();
		makeFilterJson();
		infomgr.count(dbPath, 'variant', updateLoadMsgDiv);
		if (callback != null) {
			callback();
		}
    });
}

function onClickOpenResult () {
	 var input = getEl('input');
     input.type = 'file';
     input.onchange = function (evt, ui) {
    	 onOpenResult(this);
     }
     $(input).trigger('click');
     return false;
}

function onOpenResult (input) {
	console.log(URL.createObjectURL(input.files[0]));
}

function getWidget (tabName, widgetName, widgetTitle) {
	[widgetDiv, widgetContentDiv] = 
		getDetailWidgetDivs(tabName, widgetName, widgetTitle);
	generator[tabName]['function'](widgetContentDiv, row, tabName);
	widgetDiv.clientWidth = generator[tabName]['width'];
	widgetDiv.clientHeight = generator[tabName]['height'];
	addEl(outerDiv, widgetDiv);
}

function applyWidgetSetting (level) {
	var settings = viewerWidgetSettings[level];
	if (settings == undefined)  {
		return;
	}
	var outerDiv = document.getElementById('detailcontainerdiv_' + level);
	if (outerDiv == null) {
		return;
	}
	var widgets = outerDiv.children;
	if (widgets.length > 0) {
		var items = Packery.data(outerDiv).items;
		var widgetsInLayout = [];
		var widgetCount = 0;
		for (var i = 0; i < settings.length; i++) {
			var setting = settings[i];
			for (var j = 0; j < items.length; j++) {
				var item = items[j];
				if (item.element.id == setting.id) {
					item.element.style.top = setting['top'];
					item.element.style.left = setting['left'];
					item.element.style.width = setting['width'];
					item.element.style.height = setting['height'];
					var tmp = items[widgetCount];
					items[widgetCount] = item;
					items[j] = tmp;
					widgetCount++;
					break;
				}
			}
		}
		$(outerDiv).packery();
	}
}

function applyTableSetting (level) {
	var settings = tableSettings[level];
	if (settings == undefined) {
		return;
	}
	var $grid = $grids[level];
	var colGroups = $grid.pqGrid('option', 'colModel');
	var newColModel = [];
	for (var i = 0; i < settings.length; i++) {
		var colGroupSetting = settings[i];
		var colGroupColsSetting = colGroupSetting.cols;
		for (var j = 0; j < colGroups.length; j++) {
			var colGroup = colGroups[j];
			if (colGroup.title == colGroupSetting.title) {
				newColModel.push(colGroup);
				newColModel.colModel = [];
				var cols = colGroup.colModel;
				for (k = 0; k < colGroupColsSetting.length; k++) {
					var colSetting = colGroupColsSetting[k];
					for (l = 0; l < cols.length; l++) {
						var col = cols[l];
						if (col.col == colSetting.col) {
							col.width = colSetting.width;
							newColModel.colModel.push(col);
							break;
						}
					}
				}
			}
		}
	}
	console.log(newColModel);
	$grid.pqGrid('option', 'colModel', newColModel);
	$grid.pqGrid('refresh');
}

function loadLayoutSetting (name, callback) {
	loadTableSetting(name, null);
	loadWidgetSetting(name, callback);
	lastUsedLayoutName = name;
}

function loadLayoutSettingAs () {
	$.get('rest/service/getlayoutsavenames', {'dbpath': dbPath}).done(function (response) {
		var names = '' + JSON.parse(response.replace(/'/g, '"'));
		var name = null;
		if (names != '') {
			name = prompt('Please enter layout name to load. Saved layout names are ' + names, lastUsedLayoutName);
			if (name != null) {
				loadLayoutSetting(name, null);
			}
		} else {
			alert('No layout has been saved.');
		}
	});
}

function loadFilterSettingAs () {
	$.get('rest/service/getfiltersavenames', {'dbpath': dbPath}).done(function (response) {
		var names = '' + JSON.parse(response.replace(/'/g, '"'));
		var name = null;
		if (names != '') {
			name = prompt('Please enter filter name to load. Saved filter names are ' + names, lastUsedLayoutName);
			if (name != null) {
				loadFilterSetting(name, null);
			}
		} else {
			alert('No filter has been saved.');
		}
	});
}

function loadWidgetSetting (name, callback) {
	$.get('rest/service/loadwidgetsetting', {'dbpath': dbPath, 'name': name}).done(function (response) {
		writeLogDiv('Widget setting loaded');
		response = response.replace(/'/g, '"');
		var data = JSON.parse(response);
		loadedViewerWidgetSettings = data['widgetSettings'];
		viewerWidgetSettings = loadedViewerWidgetSettings;
		if (currentTab == 'variant' || currentTab == 'gene') {
			applyWidgetSetting(currentTab);
		}
		if (callback != null) {
			callback();
		}
    });
}

function loadTableSetting (name, callback) {
	$.get('rest/service/loadtablesetting', {'dbpath': dbPath, 'name': name}).done(function (response) {
		writeLogDiv('Table setting loaded');
		response = response.replace(/'/g, '"');
		var data = JSON.parse(response);
		loadedTableSettings = data['tableSettings'];
		tableSettings = loadedTableSettings;
		if (currentTab == 'variant' || currentTab == 'gene') {
			applyTableSetting(currentTab);
		}
		if (callback != null) {
			callback();
		}
    });
}