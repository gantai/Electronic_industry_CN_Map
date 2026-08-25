$md = (Get-ChildItem "D:\Archive\转换稿\地方志\*第三章.md").FullName
$fx = (Get-ChildItem "D:\Archive\转换稿\地方志\*.fixes.tsv").FullName
python tools\gazetteer\gaz.py book $md --city Beijing --min-mentions 1 --fixes $fx
