<?php
$id = htmlspecialchars($_GET["id"]);
$id = str_replace(array("."), "", $id);


$file_name = "/data/tmp/dv/dv_" . $id . ".json";
if(file_exists($file_name)) {
	header('Content-Description: File Transfer');
    header('Content-Type: application/json');
    header('Content-Length: ' . filesize($file_name));
    header("Content-encoding: gzip");
    header('Content-Disposition: attachment; filename="'.basename($file_name).'"');
    header('Expires: 0');
    header('Cache-Control: must-revalidate');
    header('Pragma: public');
    readfile($file_name);
    exit;
} else {
	echo $file_name . " doesn't exist";
}
?>