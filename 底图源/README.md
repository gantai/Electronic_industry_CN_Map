# 底图源稿

放**原样下载**的行政区划 GeoJSON。这里的东西是原料,不是成品 ——
成品是 `src/city.geo.json`,由 `tools/geo/添底图.py` 从这里生成。

与 `转换稿/` 是一个道理:那边放志书的转换稿,这边放底图的源文件。

## 放什么

geoBoundaries 的 **CHN ADM3(simplified)** —— `src/city.geo.json` 里现有的
上海 16 个区就出自它,同一来源才好并在一处。

    https://www.geoboundaries.org/  →  China → ADM3 → simplified

下载到的是一个 zip,里头除了 `.geojson`,还有 shapefile(`.shp/.dbf/.shx/.prj`)、
topojson、预览图 —— **整包几十上百 MB,一样也别提交**。解开,只取
`geoBoundaries-CHN-ADM3_simplified.geojson` 那一个,丢进这个目录。

> [!important] 先切一刀再提交
> 全国 ADM3 有两千多个区县,几十 MB。**git 会把它永远留在历史里** ——
> 删掉也还在,仓库从此背着这几十 MB。所以先切出要用的那一个市:
>
> ```powershell
> cd D:\Coding\CN_Map
> python tools\geo\添底图.py "底图源\geoBoundaries-CHN-ADM3_simplified.geojson" 北京 --save-subset
> ```
>
> 它在这个目录里写出 `北京-区界.geojson`(几百 KB),**把原来那个大文件删掉**
> 再提交。留下的那份小的既是原料,也是出处的凭据。

> [!bug] 大文件是**故意**挡在 git 之外的,不是出错
> `.gitignore` 里列着这几种名字,**不限目录** —— 下载落在仓库哪一层都挡得住:
> ```
> geoBoundaries-*/
> geoBoundaries-*.zip
> **/geoBoundaries-CHN-ADM*
> ```
> 所以原样下载的那一份 `git status` 里根本看不见,提交也带不上 —— 这是拦着
> 它进历史。切出一市之后那份 `北京-区界.geojson` 不在此列,照常提交。
>
> 真要连原始文件一并入库(存档考虑),`git add -f 底图源\那个文件名` 可以
> 越过 —— 但先想清楚:**几十 MB 进了历史就取不出来了**。

## 从这里到地图

```powershell
cd D:\Coding\CN_Map
python tools\geo\添底图.py "底图源\北京-区界.geojson" 北京            # 先看认出了哪些区
python tools\geo\添底图.py "底图源\北京-区界.geojson" 北京 --write    # 并进 src/city.geo.json
```

坐标取到小数点后四位(约 11 米),与上海那批同一精度。

## 出处照录

`src/city.geo.json` 的 `attribution` 里记着来源与许可(geoBoundaries,CC BY 4.0)。
换了别的来源,那一行也要跟着改 —— 界线是从哪儿来的,得说得出。

> [!note] 当代政区,不是历史政区
> geoBoundaries 给的是今天的界线。北京的**崇文区、宣武区** 2010 年已并入
> 东城、西城,所以志书里「崇文区龙潭路3号」这样的地址,会落在今东城、西城
> 的界内。这一点在 `city.geo.json` 的 note 里也写着。
