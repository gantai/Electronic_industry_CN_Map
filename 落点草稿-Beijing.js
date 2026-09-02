/* 按路排的落点草稿 —— Beijing,41 家、36 条不重复的地址、32 条路。

   一条路一段,同一条路的门牌摆在一处:开着地图从街这头看到那头,
   顺次把 lat / lng 填上,比一家一家查省事,也不容易填串。

   填完把整段粘进 src/geocode.js 的 PLACES 里。**只填查得准的**;
   拿不准的整行留着不动 —— 空着的照旧落在市中心并标「坐标待定位」,
   那是老实话,胡填一个才是坏事。
*/

  /* ---- 酒仙桥路 ---- 10 家,5 个门牌,朝阳区 */
  "北京东方电子集团股份有限公司": { lat: null, lng: null, district: "朝阳", precision: "street", note: "酒仙桥路10号" },
  "北京东光电工厂": { lat: null, lng: null, district: "朝阳", precision: "street", note: "酒仙桥路12号" },
  "北京有线电总厂": { lat: null, lng: null, district: "朝阳", precision: "street", note: "酒仙桥路14号" },
  "北京国际交换系统有限公司": { lat: null, lng: null, district: "朝阳", precision: "street", note: "酒仙桥路14号" },
  //   ↑ 同一个门牌 酒仙桥路14号 底下 2 家,坐标填一样的即可
  "北京无线电工具设备厂": { lat: null, lng: null, district: "朝阳", precision: "street", note: "酒仙桥路2号" },
  "北京晨星无线电器材厂": { lat: null, lng: null, district: "朝阳", precision: "street", note: "酒仙桥路2号" },
  "北京第一无线电器材厂": { lat: null, lng: null, district: "朝阳", precision: "street", note: "酒仙桥路2号" },
  //   ↑ 同一个门牌 酒仙桥路2号 底下 3 家,坐标填一样的即可
  "北京第二无线电器材厂": { lat: null, lng: null, district: "朝阳", precision: "street", note: "酒仙桥路4号" },
  "北京电子动力公司": { lat: null, lng: null, district: "朝阳", precision: "street", note: "酒仙桥路4号" },
  "北京飞行电子总公司": { lat: null, lng: null, district: "朝阳", precision: "street", note: "酒仙桥路4号" },
  //   ↑ 同一个门牌 酒仙桥路4号 底下 3 家,坐标填一样的即可

  /* ---- 东四北大街 ---- 1 家,1 个门牌,东城区 */
  "北京电视设备厂": { lat: null, lng: null, district: "东城", precision: "street", note: "东四北大街107号" },

  /* ---- 东环北路 ---- 1 家,1 个门牌 */
  "北京核仪器厂": { lat: null, lng: null, district: "", precision: "street", note: "东环北路42号" },

  /* ---- 东铁匠营横七条 ---- 1 家,1 个门牌,丰台区 */
  "北京广播电视配件一厂": { lat: null, lng: null, district: "丰台", precision: "street", note: "东铁匠营横七条30号" },

  /* ---- 今四环胡同 ---- 1 家,1 个门牌,西城区 */
  "北京广播器材厂": { lat: null, lng: null, district: "西城", precision: "street", note: "今四环胡同4号" },

  /* ---- 光明西路 ---- 1 家,1 个门牌,崇文区 */
  "北京显像管总厂": { lat: null, lng: null, district: "崇文", precision: "street", note: "光明西路1号" },

  /* ---- 北京站东街 ---- 1 家,1 个门牌,东城区 */
  "北京市无线电元件六厂": { lat: null, lng: null, district: "东城", precision: "street", note: "北京站东街10号" },

  /* ---- 北洼路 ---- 1 家,1 个门牌,海淀区 */
  "北京飞利浦有限公司": { lat: null, lng: null, district: "海淀", precision: "street", note: "北洼路4号" },

  /* ---- 双桥西里 ---- 1 家,1 个门牌 */
  "北京701厂": { lat: null, lng: null, district: "", precision: "street", note: "双桥西里7号" },

  /* ---- 古城北路 ---- 1 家,1 个门牌,石景山区 */
  "北京无线电元件四厂": { lat: null, lng: null, district: "石景山", precision: "street", note: "古城北路甲4号" },

  /* ---- 学院南路 ---- 1 家,1 个门牌,海淀区 */
  "北京长城无线电厂": { lat: null, lng: null, district: "海淀", precision: "street", note: "学院南路34号" },

  /* ---- 学院路 ---- 1 家,1 个门牌,海淀区 */
  "北京大华无线电仪器厂": { lat: null, lng: null, district: "海淀", precision: "street", note: "学院路5号" },

  /* ---- 家来街月台胡同 ---- 1 家,1 个门牌,西城区 */
  "北京市调谐器厂": { lat: null, lng: null, district: "西城", precision: "street", note: "家来街月台胡同18号" },

  /* ---- 将台路 ---- 1 家,1 个门牌,朝阳区 */
  "北京邮电通信设备厂": { lat: null, lng: null, district: "朝阳", precision: "street", note: "将台路5号" },

  /* ---- 幸福三村北街 ---- 1 家,1 个门牌,朝阳区 */
  "北京市半导体器件一厂": { lat: null, lng: null, district: "朝阳", precision: "street", note: "幸福三村北街1号" },

  /* ---- 广安门内德泉胡同 ---- 1 家,1 个门牌,宣武区 */
  "北京市电声器材总厂": { lat: null, lng: null, district: "宣武", precision: "street", note: "广安门内德泉胡同10号" },

  /* ---- 建国门外东三环南路 ---- 1 家,1 个门牌,朝阳区 */
  "中国惠普有限公司": { lat: null, lng: null, district: "朝阳", precision: "street", note: "建国门外东三环南路2号" },

  /* ---- 建国门外砖厂胡同 ---- 1 家,1 个门牌 */
  "北京市可控硅元件厂": { lat: null, lng: null, district: "", precision: "street", note: "建国门外砖厂胡同12号" },

  /* ---- 德胜门外五路通 ---- 1 家,1 个门牌,西城区 */
  "北京半导体器件五厂": { lat: null, lng: null, district: "西城", precision: "street", note: "德胜门外五路通14号" },

  /* ---- 德胜门外后九条小市口胡同 ---- 1 家,1 个门牌,西城区 */
  "北京市无线电元件一厂": { lat: null, lng: null, district: "西城", precision: "street", note: "德胜门外后九条小市口胡同1号" },

  /* ---- 德胜门外塔院胡同 ---- 1 家,1 个门牌,西城区 */
  "北京市无线电元件二厂": { lat: null, lng: null, district: "西城", precision: "street", note: "德胜门外塔院胡同8号" },

  /* ---- 新街口外大街 ---- 1 家,1 个门牌,西城区 */
  "北京通信元件厂": { lat: null, lng: null, district: "西城", precision: "street", note: "新街口外大街28号" },

  /* ---- 朝阳门外二条 ---- 1 家,1 个门牌 */
  "北京市无线电元件十厂": { lat: null, lng: null, district: "", precision: "street", note: "朝阳门外二条67号" },

  /* ---- 深沟村 ---- 1 家,1 个门牌,朝阳区 */
  "北京无线电元件九厂": { lat: null, lng: null, district: "朝阳", precision: "street", note: "深沟村" },

  /* ---- 白石桥络 ---- 1 家,1 个门牌,海淀区 */
  "北京京海集团公司": { lat: null, lng: null, district: "海淀", precision: "street", note: "白石桥络33号" },

  /* ---- 福长街四条 ---- 1 家,1 个门牌,宣武区 */
  "北京无线电仪器厂": { lat: null, lng: null, district: "宣武", precision: "street", note: "福长街四条4号" },

  /* ---- 符台路 ---- 1 家,1 个门牌,朝阳区 */
  "北京无线电仪器二厂": { lat: null, lng: null, district: "朝阳", precision: "street", note: "符台路2号" },

  /* ---- 苏州街 ---- 1 家,1 个门牌,海淀区 */
  "北京飞达电子集团公司": { lat: null, lng: null, district: "海淀", precision: "street", note: "苏州街75号" },

  /* ---- 酒仙桥万红路 ---- 1 家,1 个门牌,朝阳区 */
  "北京建中机器厂": { lat: null, lng: null, district: "朝阳", precision: "street", note: "酒仙桥万红路1号" },

  /* ---- 酒仙桥北路 ---- 1 家,1 个门牌,朝阳区 */
  "北京·松下彩色显像管有限公司": { lat: null, lng: null, district: "朝阳", precision: "street", note: "酒仙桥北路9号" },

  /* ---- 酒仙桥南路 ---- 1 家,1 个门牌,朝阳区 */
  "北京电视配件三厂": { lat: null, lng: null, district: "朝阳", precision: "street", note: "酒仙桥南路5号" },

  /* ---- 龙潭路 ---- 1 家,1 个门牌,崇文区 */
  "北京市半导体器件三厂": { lat: null, lng: null, district: "崇文", precision: "street", note: "龙潭路3号" },
