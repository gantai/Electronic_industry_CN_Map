export const YEAR_MIN = 1949, YEAR_MAX = 2005;

export const TYPE_META = {
  factory:   { label: "工厂",   color: "#F2C14E" },
  institute: { label: "研究所", color: "#7ED8E8" },
  group:     { label: "联合体", color: "#C9B8FF" },
};
export const TYPE_FROM_ZH = { "工厂": "factory", "研究所": "institute", "联合体": "group" };

export const EVENT_META = {
  "分立": { color: "#F2C14E", dash: null,    slug: "split"  },
  "合并": { color: "#7ED8E8", dash: null,    slug: "merge"  },
  "援建": { color: "#D8E7F6", dash: [6, 5],  slug: "aid"    },
  "迁建": { color: "#D8E7F6", dash: [2, 5],  slug: "move"   },
  "协作": { color: "#8FA9C9", dash: [1, 6],  slug: "collab" },
};
export const HUB_LABELS = { jxq: "北京·酒仙桥电子工业区", sh: "上海" };

export const STYPE_LABEL = { entity: "新增节点", event: "新增沿革事件", correction: "订正信息", citation: "新增引文" };
