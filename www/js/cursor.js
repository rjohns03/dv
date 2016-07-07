function getPath(startAngle, endAngle, innerRadius, outerRadius, centerX, centerY){
    startAngle -= Math.PI / 2;
    endAngle -= Math.PI/ 2;
    M1=[0, 0];
    A1=[outerRadius, outerRadius, 0, ~~(endAngle - startAngle > Math.PI), 1, 0, 0];
    M2=[0, 0];
    A2=[innerRadius, innerRadius, 0, ~~(endAngle - startAngle > Math.PI), 0, 0, 0];
    M1[0] = outerRadius * Math.cos(startAngle) + centerX;
    M1[1] = outerRadius * Math.sin(startAngle) + centerY;
    A1[5] = outerRadius * Math.cos(endAngle) + centerX;
    A1[6] = outerRadius * Math.sin(endAngle) + centerY; 
    M2[0] = innerRadius * Math.cos(endAngle) + centerX;
    M2[1] = innerRadius * Math.sin(endAngle) + centerY;      
    A2[5] = innerRadius * Math.cos(startAngle) + centerX;
    A2[6] = innerRadius * Math.sin(startAngle) + centerY; 
    var circle_var = " L";
    if (endAngle - startAngle >= Math.PI * 2 - 0.00001) {
        A1[5] -= 0.0001;
        A2[5] += 0.0001;
        circle_var = " M";
    }
    else {
    	A2.push("Z");
    }
    var d = "M" + M1.join(" ") + " A" + A1.join(" ") + circle_var + M2.join(" ") + " A" + A2.join(" ");
    return d;
}

var Cursor = function(radius) {
	this.MAX_DEPTH = 10;
	if(tree_depth < this.MAX_DEPTH) {
		this.MAX_DEPTH = tree_depth;
	}
	this.radius = radius;

	var svg = $("#circle")
	this.center = {"x": svg.width() / 2, "y": svg.height() / 2};
	this.inner_pad = 100;
	this.thickness = (this.radius - (this.inner_pad / 2)) / (this.MAX_DEPTH + 2);
	this.layers = 0;
	this.cursor = {};
};

Cursor.prototype.getLastProgression = function(layer_no) {
	if(layer_no > 1) {
		return this.cursor[layer_no - 1].progression;
	} else {
		return 0;
	}
};

Cursor.prototype.addLayer = function() {
	this.layers++;
	var inner_radius = this.inner_pad + (this.layers - 1)*this.thickness
	this.cursor[this.layers] = {"progression": this.getLastProgression(), "innerRadius": inner_radius, "outerRadius": inner_radius + this.thickness, "count": 0}
};

Cursor.prototype.getPath = function(node, parent, total_size, depth) {
	if(depth > this.layers) {
		this.addLayer();
	}
	var layer = this.cursor[depth];
	var piece_thickness = Math.PI * 2 * (node[value_type] / total_size);
	node.thickness = piece_thickness;

	if(depth > this.MAX_DEPTH || piece_thickness < 0.005) {
		return;
	}
	var path = getPath(parent.progression, parent.progression + piece_thickness, layer.innerRadius, layer.outerRadius, this.center.y, this.center.x);
	node.progression = parent.progression;
	parent.progression += piece_thickness;
	layer.count++;
	return path;
};
