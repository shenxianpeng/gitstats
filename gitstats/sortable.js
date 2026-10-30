/*
Table sorting script  by Joost de Valk, check it out at http://www.joostdevalk.nl/code/sortable-table/.
Based on a script from http://www.kryogenix.org/code/browser/sorttable/.
Distributed under the MIT license: http://www.kryogenix.org/code/browser/licence.html .

Copyright (c) 1997-2007 Stuart Langridge, Joost de Valk.

Version 1.5.7
*/

/* You can change these values */
/* gitstats: sort arrows are drawn by CSS from span.sortarrow[data-sort] (none/asc/desc)
   instead of arrow-*.gif images, so they follow the light/dark theme. */
var europeandate = true;
var alternate_row_colors = true;

/* Don't change anything below this unless you know what you're doing */
addEvent(window, "load", sortables_init);

var SORT_COLUMN_INDEX;
var thead = false;

function sortables_init() {
	// Find all tables with class sortable and make them sortable
	if (!document.getElementsByTagName) return;
	tbls = document.getElementsByTagName("table");
	for (ti=0;ti<tbls.length;ti++) {
		thisTbl = tbls[ti];
		if (((' '+thisTbl.className+' ').indexOf("sortable") != -1) && (thisTbl.id)) {
			ts_makeSortable(thisTbl);
		}
	}
}

function ts_makeSortable(t) {
	if (t.rows && t.rows.length > 0) {
		if (t.tHead && t.tHead.rows.length > 0) {
			var firstRow = t.tHead.rows[t.tHead.rows.length-1];
			thead = true;
		} else {
			var firstRow = t.rows[0];
		}
	}
	if (!firstRow) return;

	// We have a first row: assume it's the header, and make its contents clickable links
	for (var i=0;i<firstRow.cells.length;i++) {
		var cell = firstRow.cells[i];
		if (cell.className != "unsortable" && cell.className.indexOf("unsortable") == -1) {
			// gitstats: the header's own content goes into the link as it is;
			// its innerText would be what CSS shows, e.g. upper-cased
			var link = document.createElement("a");
			link.href = "#";
			link.className = "sortheader";
			link.setAttribute("onclick", "ts_resortTable(this, " + i + ");return false;");
			while (cell.firstChild) link.appendChild(cell.firstChild);
			var arrow = document.createElement("span");
			arrow.className = "sortarrow";
			arrow.setAttribute("data-sort", "none");
			arrow.setAttribute("aria-hidden", "true");
			link.appendChild(arrow);
			cell.appendChild(link);
		}
	}
	if (alternate_row_colors) {
		alternate(t);
	}
}

function ts_getInnerText(el) {
	if (typeof el == "string") return el;
	if (typeof el == "undefined") { return el };
	if (el.innerText) return el.innerText;	//Not needed but it is faster
	var str = "";

	var cs = el.childNodes;
	var l = cs.length;
	for (var i = 0; i < l; i++) {
		switch (cs[i].nodeType) {
			case 1: //ELEMENT_NODE
				str += ts_getInnerText(cs[i]);
				break;
			case 3:	//TEXT_NODE
				str += cs[i].nodeValue;
				break;
		}
	}
	return str;
}

// A cell with nothing to sort by: empty, or a dash that stands for no value.
// Such cells go last, whichever way the column is sorted.
function ts_isBlank(text) {
	return text == "" || text == "\u2014" || text == "\u2013" || text == "-" || text.substr(0,4) == "<!--";
}

// What a cell is sorted by: its data-sort value when it has one (e.g. the
// number of days behind "1.9 yr"), else its text.
function ts_cellText(row, column) {
	var cell = row.cells[column];
	if (!cell) return "";
	var key = cell.getAttribute("data-sort");
	return key !== null ? key : trim(ts_getInnerText(cell));
}

// The sort a column takes, worked out once, from all its values: a later
// click finds the rows in another order, and must not sort them another way.
function ts_columnSort(t, column, rows) {
	if (!t.ts_sorts) t.ts_sorts = {};
	if (t.ts_sorts[column] !== undefined) return t.ts_sorts[column];
	var numeric = 0, dates = 0, values = 0;
	for (var row of rows) {
		var itm = ts_cellText(row, column);
		if (ts_isBlank(itm)) continue;
		values++;
		// numbers, ignoring stuff in () after them
		if (itm.match(/^-?\d[\d,.]*(E[-+]\d+)?%?( \(.*\))?$/)) numeric++;
		if (itm.match(/^\d\d[/.-][a-zA-Z]{3}[/.-]\d{4}$/) || itm.match(/^\d\d[/.-]\d\d[/.-]\d\d(\d\d)?$/)) dates++;
	}
	var sortfn = null;
	if (values) {
		sortfn = ts_sort_caseinsensitive;
		if (dates == values) sortfn = ts_sort_date;
		else if (numeric == values) sortfn = ts_sort_numeric;
	}
	t.ts_sorts[column] = sortfn;
	return sortfn;
}

function ts_resortTable(lnk, clid) {
	var span, i, j, k;
	for (var ci=0;ci<lnk.childNodes.length;ci++) {
		if (lnk.childNodes[ci].tagName && lnk.childNodes[ci].tagName.toLowerCase() == 'span') span = lnk.childNodes[ci];
	}
	var td = lnk.parentNode;
	var column = clid || td.cellIndex;
	var t = getParent(td,'TABLE');
	if (t.rows.length <= 1) return;
	var newRows = new Array();
	for (k=0;k<t.tBodies.length;k++) {
		// without a <thead>, the first row of the body is the header: skip it
		for (j=(thead ? 0 : 1);j<t.tBodies[k].rows.length;j++) {
			newRows[newRows.length] = t.tBodies[k].rows[j];
		}
	}
	var sortfn = ts_columnSort(t, column, newRows);
	if (!sortfn) return;
	SORT_COLUMN_INDEX = column;
	var blankRows = new Array();
	var valueRows = new Array();
	for (i=0;i<newRows.length;i++) {
		if (ts_isBlank(ts_cellText(newRows[i], column))) blankRows[blankRows.length] = newRows[i];
		else valueRows[valueRows.length] = newRows[i];
	}
	newRows = valueRows;
	newRows.sort(sortfn);
	if (span.getAttribute("sortdir") == 'down') {
			ARROW = 'desc';
			newRows.reverse();
			span.setAttribute('sortdir','up');
	} else {
			ARROW = 'asc';
			span.setAttribute('sortdir','down');
	}
	newRows = newRows.concat(blankRows);
    // We appendChild rows that already exist to the tbody, so it moves them rather than creating new ones
    // don't do sortbottom rows
    for (i=0; i<newRows.length; i++) {
		if (!newRows[i].className || (newRows[i].className && (newRows[i].className.indexOf('sortbottom') == -1))) {
			t.tBodies[0].appendChild(newRows[i]);
		}
	}
    // do sortbottom rows only
    for (i=0; i<newRows.length; i++) {
		if (newRows[i].className && (newRows[i].className.indexOf('sortbottom') != -1))
			t.tBodies[0].appendChild(newRows[i]);
	}
	// Delete any other arrows there may be showing
	var allspans = document.getElementsByTagName("span");
	for (var ci=0;ci<allspans.length;ci++) {
		if (allspans[ci].className == 'sortarrow') {
			if (getParent(allspans[ci],"table") == getParent(lnk,"table")) { // in the same table as us?
				allspans[ci].setAttribute('data-sort', 'none');
				allspans[ci].parentNode.parentNode.removeAttribute('aria-sort');
			}
		}
	}
	span.setAttribute('data-sort', ARROW);
	td.setAttribute('aria-sort', ARROW == 'asc' ? 'ascending' : 'descending');
	alternate(t);
}

function getParent(el, pTagName) {
	if (el == null) {
		return null;
	} else if (el.nodeType == 1 && el.tagName.toLowerCase() == pTagName.toLowerCase()) {
		return el;
	} else {
		return getParent(el.parentNode, pTagName);
	}
}

function sort_date(date) {
	// y2k notes: two digit years less than 50 are treated as 20XX, greater than 50 are treated as 19XX
	dt = "00000000";
	if (date.length == 11) {
		mtstr = date.substr(3,3);
		mtstr = mtstr.toLowerCase();
		switch(mtstr) {
			case "jan": var mt = "01"; break;
			case "feb": var mt = "02"; break;
			case "mar": var mt = "03"; break;
			case "apr": var mt = "04"; break;
			case "may": var mt = "05"; break;
			case "jun": var mt = "06"; break;
			case "jul": var mt = "07"; break;
			case "aug": var mt = "08"; break;
			case "sep": var mt = "09"; break;
			case "oct": var mt = "10"; break;
			case "nov": var mt = "11"; break;
			case "dec": var mt = "12"; break;
			// default: var mt = "00";
		}
		dt = date.substr(7,4)+mt+date.substr(0,2);
		return dt;
	} else if (date.length == 10) {
		if (europeandate == false) {
			dt = date.substr(6,4)+date.substr(0,2)+date.substr(3,2);
			return dt;
		} else {
			dt = date.substr(6,4)+date.substr(3,2)+date.substr(0,2);
			return dt;
		}
	} else if (date.length == 8) {
		yr = date.substr(6,2);
		if (parseInt(yr) < 50) {
			yr = '20'+yr;
		} else {
			yr = '19'+yr;
		}
		if (europeandate == true) {
			dt = yr+date.substr(3,2)+date.substr(0,2);
			return dt;
		} else {
			dt = yr+date.substr(0,2)+date.substr(3,2);
			return dt;
		}
	}
	return dt;
}

function ts_sort_date(a,b) {
	dt1 = sort_date(ts_cellText(a, SORT_COLUMN_INDEX));
	dt2 = sort_date(ts_cellText(b, SORT_COLUMN_INDEX));

	if (dt1==dt2) {
		return 0;
	}
	if (dt1<dt2) {
		return -1;
	}
	return 1;
}
function ts_sort_numeric(a,b) {
	var aa = clean_num(ts_cellText(a, SORT_COLUMN_INDEX));
	var bb = clean_num(ts_cellText(b, SORT_COLUMN_INDEX));
	return compare_numeric(aa,bb);
}
function compare_numeric(a,b) {
	var a = parseFloat(a);
	a = (isNaN(a) ? 0 : a);
	var b = parseFloat(b);
	b = (isNaN(b) ? 0 : b);
	return a - b;
}
// gitstats: text is compared the way people read it: case aside, and the
// numbers in it by value, so that v0.9 comes before v0.10
var ts_collator = new Intl.Collator(undefined, {numeric: true, sensitivity: "base"});
function ts_sort_caseinsensitive(a,b) {
	return ts_collator.compare(ts_cellText(a, SORT_COLUMN_INDEX), ts_cellText(b, SORT_COLUMN_INDEX));
}
function ts_sort_default(a,b) {
	aa = ts_getInnerText(a.cells[SORT_COLUMN_INDEX]);
	bb = ts_getInnerText(b.cells[SORT_COLUMN_INDEX]);
	if (aa==bb) {
		return 0;
	}
	if (aa<bb) {
		return -1;
	}
	return 1;
}
function addEvent(elm, evType, fn, useCapture)
// addEvent and removeEvent
// cross-browser event handling for IE5+,	NS6 and Mozilla
// By Scott Andrew
{
	if (elm.addEventListener){
		elm.addEventListener(evType, fn, useCapture);
		return true;
	} else if (elm.attachEvent){
		var r = elm.attachEvent("on"+evType, fn);
		return r;
	} else {
		alert("Handler could not be removed");
	}
}
// gitstats: the number a cell starts with, without its thousands separators:
// "127 (78.4% of 162)" is 127, not 12778.4162
function clean_num(str) {
	var match = str.replace(/,/g, "").match(/^-?\d*\.?\d+(E[-+]\d+)?/i);
	return match ? match[0] : "";
}
function trim(s) {
	return s.replace(/^\s+|\s+$/g, "");
}
function alternate(table) {
	// Take object table and get all it's tbodies.
	var tableBodies = table.getElementsByTagName("tbody");
	// Loop through these tbodies
	for (var i = 0; i < tableBodies.length; i++) {
		// Take the tbody, and get all it's rows
		var tableRows = tableBodies[i].getElementsByTagName("tr");
		// Loop through these rows
		// Start at 1 because we want to leave the heading row untouched
		for (var j = 0; j < tableRows.length; j++) {
			// Check if j is even, and apply classes for both possible results
			if ( (j % 2) == 0  ) {
				if ( !(tableRows[j].className.indexOf('odd') == -1) ) {
					tableRows[j].className = tableRows[j].className.replace('odd', 'even');
				} else {
					if ( tableRows[j].className.indexOf('even') == -1 ) {
						tableRows[j].className += " even";
					}
				}
			} else {
				if ( !(tableRows[j].className.indexOf('even') == -1) ) {
					tableRows[j].className = tableRows[j].className.replace('even', 'odd');
				} else {
					if ( tableRows[j].className.indexOf('odd') == -1 ) {
						tableRows[j].className += " odd";
					}
				}
			}
		}
	}
}
