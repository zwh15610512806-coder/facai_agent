/**
 * 法采新媒体运营Agent PRD文档生成脚本
 * 使用 PptxGenJS 生成专业产品需求文档
 */
const pptxgen = require("pptxgenjs");

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.title = "法采短视频脚本生成Agent — 产品需求文档";
pres.author = "法采运营团队";

// ========== 配色系统 ==========
const C = {
  bg:         "FDF8F3",   // 主背景（暖米色）
  dark:       "2C1A0E",   // 深棕（主标题）
  amber:      "D97706",   // 琥珀橙（品牌色）
  amberLight: "FDE68A",   // 淡黄（标签/高亮）
  warm1:      "92400E",   // 深琥珀（副标题）
  warm2:      "B45309",   // 中琥珀
  text2:      "6B7280",   // 浅灰文字
  white:      "FFFFFF",
  card:       "FFFFFF",
  border:     "E5D4B8",   // 暖色边框
  green:      "059669",   // 成功绿
  slate:      "475569",
  headerBg:   "3B1F08",   // 深咖（标题栏背景）
};

const makeShadow = () => ({ type: "outer", blur: 5, offset: 2, angle: 135, color: "000000", opacity: 0.08 });

// ========== 辅助函数：绘制导航栏 ==========
function addNav(slide, activeIdx) {
  // 顶部导航背景
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.42,
    fill: { color: C.headerBg }, line: { color: C.headerBg }
  });
  // 品牌名
  slide.addText("🍞 法采新媒体运营Agent · PRD", {
    x: 0.28, y: 0, w: 4, h: 0.42,
    fontSize: 11, color: C.white, bold: true, valign: "middle", margin: 0
  });
  // 章节列表
  const navItems = ["概述", "用户", "功能", "流程", "架构", "数据模型", "API", "部署", "路线图"];
  navItems.forEach((item, i) => {
    const isActive = i === activeIdx;
    slide.addText(item, {
      x: 4.6 + i * 0.6, y: 0, w: 0.56, h: 0.42,
      fontSize: 9, color: isActive ? C.amber : "D5C4A1",
      bold: isActive, valign: "middle", align: "center", margin: 0
    });
    if (isActive) {
      slide.addShape(pres.shapes.RECTANGLE, {
        x: 4.6 + i * 0.6, y: 0.36, w: 0.56, h: 0.06,
        fill: { color: C.amber }, line: { color: C.amber }
      });
    }
  });
}

// ========== 辅助函数：绘制卡片 ==========
function addCard(slide, x, y, w, h, opts = {}) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h,
    fill: { color: opts.fill || C.card },
    line: { color: opts.border || C.border, width: 1 },
    shadow: opts.shadow !== false ? makeShadow() : undefined,
    rectRadius: opts.radius || 0,
  });
}

// ========== 辅助函数：左侧色条标题 ==========
function addSectionTitle(slide, x, y, text, subtext) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w: 0.07, h: subtext ? 0.65 : 0.45,
    fill: { color: C.amber }, line: { color: C.amber }
  });
  slide.addText(text, {
    x: x + 0.14, y, w: 9, h: 0.36,
    fontSize: 18, bold: true, color: C.dark, valign: "middle", margin: 0
  });
  if (subtext) {
    slide.addText(subtext, {
      x: x + 0.14, y: y + 0.36, w: 9, h: 0.28,
      fontSize: 11, color: C.text2, valign: "middle", margin: 0
    });
  }
}

// ========================================================================
// Slide 1 — 封面
// ========================================================================
{
  const slide = pres.addSlide();
  slide.background = { color: C.headerBg };

  // 右侧暖色装饰块
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 6.8, y: 0, w: 3.2, h: 5.625,
    fill: { color: "4A2408" }, line: { color: "4A2408" }
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 7.2, y: 0, w: 2.8, h: 5.625,
    fill: { color: "5C2D0A", transparency: 30 }, line: { color: "5C2D0A" }
  });
  // 琥珀色竖条
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 6.76, y: 0, w: 0.08, h: 5.625,
    fill: { color: C.amber }, line: { color: C.amber }
  });

  // 版本标签
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.55, y: 0.62, w: 1.3, h: 0.32,
    fill: { color: C.amber }, line: { color: C.amber }
  });
  slide.addText("v1.0  PRD", {
    x: 0.55, y: 0.62, w: 1.3, h: 0.32,
    fontSize: 10, bold: true, color: C.white, align: "center", valign: "middle", margin: 0
  });

  // 主标题
  slide.addText("法采短视频", {
    x: 0.55, y: 1.12, w: 6, h: 0.85,
    fontSize: 46, bold: true, color: C.white, margin: 0
  });
  slide.addText("脚本生成 Agent", {
    x: 0.55, y: 1.9, w: 6, h: 0.85,
    fontSize: 46, bold: true, color: C.amber, margin: 0
  });
  slide.addText("产品需求文档", {
    x: 0.55, y: 2.78, w: 6, h: 0.52,
    fontSize: 22, color: "D5C4A1", margin: 0
  });

  // 分割线
  slide.addShape(pres.shapes.LINE, {
    x: 0.55, y: 3.42, w: 5.8, h: 0,
    line: { color: "6B3A1A", width: 1 }
  });

  // 元信息
  slide.addText([
    { text: "产品名称：", options: { bold: true, color: "D5C4A1" } },
    { text: "法采新媒体运营Agent  ", options: { color: C.white } },
    { text: " 版本：", options: { bold: true, color: "D5C4A1" } },
    { text: "1.0.0", options: { color: C.white } },
  ], {
    x: 0.55, y: 3.56, w: 5.8, h: 0.32,
    fontSize: 12, margin: 0
  });
  slide.addText([
    { text: "日期：", options: { bold: true, color: "D5C4A1" } },
    { text: "2026-05  ", options: { color: C.white } },
    { text: " 作者：", options: { bold: true, color: "D5C4A1" } },
    { text: "法采运营团队", options: { color: C.white } },
  ], {
    x: 0.55, y: 3.92, w: 5.8, h: 0.32,
    fontSize: 12, margin: 0
  });

  // 右侧概要
  slide.addText("项目概要", {
    x: 7.1, y: 0.55, w: 2.5, h: 0.36,
    fontSize: 13, bold: true, color: C.amber, margin: 0
  });
  const items = [
    "抖音带货脚本智能生成",
    "DeepSeek AI + 模板引擎",
    "57 款法采烘焙产品内置",
    "9 种视频类型覆盖",
    "向量检索爆款参考",
    "脚本改写功能",
    "FastAPI + SQLite",
  ];
  items.forEach((item, i) => {
    slide.addShape(pres.shapes.OVAL, {
      x: 7.12, y: 1.08 + i * 0.58, w: 0.13, h: 0.13,
      fill: { color: C.amber }, line: { color: C.amber }
    });
    slide.addText(item, {
      x: 7.32, y: 1.04 + i * 0.58, w: 2.3, h: 0.28,
      fontSize: 11, color: "E8D5BC", margin: 0
    });
  });
}

// ========================================================================
// Slide 2 — 目录
// ========================================================================
{
  const slide = pres.addSlide();
  slide.background = { color: C.bg };
  addNav(slide, -1);

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0.42, w: 10, h: 0.88,
    fill: { color: C.border }, line: { color: C.border }
  });
  slide.addText("目 录", {
    x: 0.5, y: 0.42, w: 9, h: 0.88,
    fontSize: 26, bold: true, color: C.dark, valign: "middle", margin: 0
  });
  slide.addText("CONTENTS", {
    x: 7.2, y: 0.42, w: 2.5, h: 0.88,
    fontSize: 14, color: C.text2, align: "right", valign: "middle", margin: 0
  });

  const sections = [
    ["01", "产品概述", "项目背景、核心价值与目标用户"],
    ["02", "用户研究", "使用场景与用户需求分析"],
    ["03", "功能清单", "完整功能点与优先级矩阵"],
    ["04", "用户操作流程", "生成脚本的核心交互路径"],
    ["05", "系统架构", "技术选型与模块划分"],
    ["06", "数据模型", "六张核心数据表设计"],
    ["07", "API接口", "后端接口规范与示例"],
    ["08", "部署说明", "环境依赖与启动配置"],
    ["09", "产品路线图", "已实现功能与后续规划"],
  ];

  sections.forEach(([num, title, desc], i) => {
    const col = i % 3;
    const row = Math.floor(i / 3);
    const x = 0.35 + col * 3.22;
    const y = 1.48 + row * 1.28;
    addCard(slide, x, y, 3.0, 1.08, { radius: 0.05 });
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 0.54, h: 1.08,
      fill: { color: C.amber }, line: { color: C.amber }
    });
    slide.addText(num, {
      x, y, w: 0.54, h: 1.08,
      fontSize: 18, bold: true, color: C.white, align: "center", valign: "middle", margin: 0
    });
    slide.addText(title, {
      x: x + 0.62, y: y + 0.12, w: 2.28, h: 0.38,
      fontSize: 14, bold: true, color: C.dark, margin: 0
    });
    slide.addText(desc, {
      x: x + 0.62, y: y + 0.54, w: 2.28, h: 0.4,
      fontSize: 10, color: C.text2, margin: 0
    });
  });
}

// ========================================================================
// Slide 3 — 产品概述
// ========================================================================
{
  const slide = pres.addSlide();
  slide.background = { color: C.bg };
  addNav(slide, 0);
  addSectionTitle(slide, 0.38, 0.62, "产品概述", "项目背景 · 核心价值 · 目标用户");

  // 背景卡片
  addCard(slide, 0.38, 1.3, 5.8, 1.22);
  slide.addText("项目背景", {
    x: 0.6, y: 1.36, w: 3, h: 0.3,
    fontSize: 12, bold: true, color: C.amber, margin: 0
  });
  slide.addText(
    "法采食品是专注B2B烘焙原料供应的品牌，运营团队每日需要为抖音直播与短视频创作大量带货脚本。传统人工撰写效率低、质量不稳定，且难以快速针对57款产品批量输出。本工具旨在通过AI+模板双引擎，让非专业文案的运营人员也能一键生成高转化带货脚本。",
    {
      x: 0.6, y: 1.7, w: 5.4, h: 0.74,
      fontSize: 11, color: C.slate, margin: 0
    }
  );

  // 核心价值 3卡片
  const values = [
    ["⚡", "提效", "从30分钟手写\n到30秒一键生成"],
    ["🎯", "精准", "产品卖点×脚本模板\n双重匹配"],
    ["🔁", "可复用", "爆款脚本入库\n持续学习迭代"],
  ];
  values.forEach(([icon, title, desc], i) => {
    addCard(slide, 0.38 + i * 3.12, 2.68, 2.86, 1.42, { fill: i === 1 ? "FFF8EE" : C.card });
    if (i === 1) {
      slide.addShape(pres.shapes.RECTANGLE, {
        x: 0.38 + i * 3.12, y: 2.68, w: 2.86, h: 0.08,
        fill: { color: C.amber }, line: { color: C.amber }
      });
    }
    slide.addText(icon, {
      x: 0.5 + i * 3.12, y: 2.78, w: 0.5, h: 0.5,
      fontSize: 24, margin: 0
    });
    slide.addText(title, {
      x: 0.5 + i * 3.12, y: 3.26, w: 2.6, h: 0.3,
      fontSize: 14, bold: true, color: C.dark, margin: 0
    });
    slide.addText(desc, {
      x: 0.5 + i * 3.12, y: 3.58, w: 2.6, h: 0.44,
      fontSize: 10.5, color: C.text2, margin: 0
    });
  });

  // 右侧目标用户
  addCard(slide, 6.42, 1.3, 3.2, 2.8);
  slide.addText("目标用户", {
    x: 6.6, y: 1.38, w: 2.8, h: 0.3,
    fontSize: 12, bold: true, color: C.amber, margin: 0
  });
  const users = [
    ["主要用户", "法采运营/营销团队\n（2-6人），非技术人员，\n每日使用于内容创作"],
    ["次要用户", "管理层，用于\n审查/调用生成脚本"],
  ];
  users.forEach(([type, desc], i) => {
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 6.58, y: 1.82 + i * 1.18, w: 0.07, h: 0.8,
      fill: { color: C.amber }, line: { color: C.amber }
    });
    slide.addText(type, {
      x: 6.74, y: 1.82 + i * 1.18, w: 2.7, h: 0.28,
      fontSize: 11, bold: true, color: C.dark, margin: 0
    });
    slide.addText(desc, {
      x: 6.74, y: 2.12 + i * 1.18, w: 2.7, h: 0.5,
      fontSize: 10, color: C.text2, margin: 0
    });
  });

  // 版本标签
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.38, y: 4.24, w: 1.4, h: 0.28,
    fill: { color: "FEF3C7" }, line: { color: C.amberLight }
  });
  slide.addText("当前版本：v1.0.0", {
    x: 0.38, y: 4.24, w: 1.4, h: 0.28,
    fontSize: 9, color: C.warm2, align: "center", valign: "middle", margin: 0
  });
}

// ========================================================================
// Slide 4 — 用户研究
// ========================================================================
{
  const slide = pres.addSlide();
  slide.background = { color: C.bg };
  addNav(slide, 1);
  addSectionTitle(slide, 0.38, 0.62, "用户研究", "使用场景 · 核心诉求 · 痛点分析");

  // 使用场景
  addCard(slide, 0.38, 1.3, 5.68, 2.0);
  slide.addText("典型使用场景", {
    x: 0.55, y: 1.38, w: 5, h: 0.3,
    fontSize: 12, bold: true, color: C.amber, margin: 0
  });
  slide.addText(
    "运营人员在烘焙办公室，坐于14~15寸笔记本前，环境：自然采光、厨房背景音。操作会被频繁打断——查数据、进厨房确认产品、返回修改。界面必须扫一眼即可理解，不能有复杂操作流程。",
    {
      x: 0.55, y: 1.72, w: 5.32, h: 0.52,
      fontSize: 10.5, color: C.slate, margin: 0
    }
  );

  const scenes = [
    ["📱", "日播备稿", "每日上播前快速生成\n当天主推产品脚本"],
    ["🔁", "批量制作", "为同类多款产品\n批量生成差异化版本"],
    ["✏️", "改写复用", "将市场同类爆款\n改写为法采版本"],
  ];
  scenes.forEach(([icon, t, d], i) => {
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 0.55 + i * 1.84, y: 2.32, w: 1.64, h: 0.8,
      fill: { color: i % 2 === 0 ? "FFF8EE" : C.card },
      line: { color: C.border, width: 1 }
    });
    slide.addText(`${icon} ${t}`, {
      x: 0.64 + i * 1.84, y: 2.38, w: 1.46, h: 0.26,
      fontSize: 10.5, bold: true, color: C.dark, margin: 0
    });
    slide.addText(d, {
      x: 0.64 + i * 1.84, y: 2.66, w: 1.46, h: 0.4,
      fontSize: 9.5, color: C.text2, margin: 0
    });
  });

  // 用户痛点
  addCard(slide, 0.38, 3.42, 5.68, 1.62);
  slide.addText("核心痛点", {
    x: 0.55, y: 3.5, w: 5, h: 0.3,
    fontSize: 12, bold: true, color: C.amber, margin: 0
  });
  const pains = [
    "手写脚本耗时30min+/篇，57款产品难以逐一覆盖",
    "文案水平参差不齐，同类产品重复套路，缺乏新鲜感",
    "优秀脚本无处沉淀，无法形成团队知识资产",
    "无法快速参考竞品爆款结构进行二次改写",
  ];
  pains.forEach((pain, i) => {
    slide.addShape(pres.shapes.OVAL, {
      x: 0.55, y: 3.88 + i * 0.27, w: 0.13, h: 0.13,
      fill: { color: C.amber }, line: { color: C.amber }
    });
    slide.addText(pain, {
      x: 0.76, y: 3.84 + i * 0.27, w: 5.1, h: 0.24,
      fontSize: 10.5, color: C.slate, margin: 0
    });
  });

  // 右侧用户画像
  addCard(slide, 6.3, 1.3, 3.28, 3.74);
  slide.addText("用户画像", {
    x: 6.5, y: 1.38, w: 2.9, h: 0.3,
    fontSize: 12, bold: true, color: C.amber, margin: 0
  });
  const attrs = [
    ["身份", "烘焙食品电商运营"],
    ["技能", "非技术，熟悉产品"],
    ["设备", "Windows PC / 手机"],
    ["频次", "每日使用，高频"],
    ["痛点", "效率低，质量不稳定"],
    ["期望", "快速、有说服力的脚本"],
    ["偏好", "操作极简，结果可控"],
  ];
  attrs.forEach(([k, v], i) => {
    slide.addShape(pres.shapes.LINE, {
      x: 6.45, y: 1.76 + i * 0.42, w: 2.96, h: 0,
      line: { color: C.border, width: 0.5 }
    });
    slide.addText(k, {
      x: 6.5, y: 1.78 + i * 0.42, w: 0.88, h: 0.3,
      fontSize: 10, color: C.text2, bold: true, margin: 0
    });
    slide.addText(v, {
      x: 7.46, y: 1.78 + i * 0.42, w: 2.0, h: 0.3,
      fontSize: 10, color: C.dark, margin: 0
    });
  });
}

// ========================================================================
// Slide 5 — 功能清单
// ========================================================================
{
  const slide = pres.addSlide();
  slide.background = { color: C.bg };
  addNav(slide, 2);
  addSectionTitle(slide, 0.38, 0.62, "功能清单", "核心功能 · 辅助功能 · 管理功能");

  const features = [
    {
      cat: "🤖 核心功能", color: C.amber, items: [
        ["AI脚本生成", "P0", "选产品→选类型→一键生成，DeepSeek AI驱动"],
        ["模板改写引擎", "P0", "无AI时自动降级为法采模板库填充"],
        ["9种视频类型", "P0", "黄金3秒/测评/痛点/限时/剧情/口播/开箱/工厂/展示"],
        ["随机多样化", "P0", "每次生成结果随机差异，避免重复套路"],
        ["脚本改写", "P1", "输入竞品脚本，自动改写为法采版本"],
      ]
    },
    {
      cat: "📦 产品管理", color: "0D9488", items: [
        ["产品库", "P0", "57款产品已入库，含品类/价格/卖点话术"],
        ["卖点话术", "P0", "多级卖点，按优先级排序输入AI"],
        ["产品搜索", "P1", "按名称/品类实时筛选"],
        ["CSV导入", "P1", "支持Excel/CSV批量导入产品数据"],
      ]
    },
    {
      cat: "📚 脚本库", color: "7C3AED", items: [
        ["爆款脚本库", "P0", "向量检索相似爆款作为生成参考"],
        ["参考脚本库", "P1", "存储竞品爆款脚本，辅助改写"],
        ["生成历史", "P1", "记录所有生成记录，支持复制/收藏"],
        ["存入模板库", "P2", "将好脚本一键存入爆款库复用"],
      ]
    },
    {
      cat: "⚙️ 系统功能", color: "059669", items: [
        ["在线/离线双模式", "P0", "有API Key用AI，无Key用模板"],
        ["局域网访问", "P0", "同Wi-Fi下手机/平板均可访问"],
        ["优化重生成", "P1", "输入优化要求，保持产品和类型重新生成"],
        ["高成交标记", "P2", "标记高转化率脚本供优先参考"],
      ]
    },
  ];

  features.forEach((group, gi) => {
    const x = gi < 2 ? 0.25 : 5.12;
    const y = gi % 2 === 0 ? 1.3 : 3.3;
    addCard(slide, x, y, 4.62, 1.88);
    slide.addText(group.cat, {
      x: x + 0.18, y: y + 0.1, w: 4.2, h: 0.3,
      fontSize: 11, bold: true, color: group.color, margin: 0
    });
    group.items.forEach((item, ii) => {
      const [name, pri, desc] = item;
      const priColor = pri === "P0" ? "DC2626" : pri === "P1" ? C.amber : C.text2;
      slide.addText(name, {
        x: x + 0.18, y: y + 0.44 + ii * 0.33, w: 1.3, h: 0.28,
        fontSize: 10.5, bold: true, color: C.dark, margin: 0
      });
      slide.addShape(pres.shapes.RECTANGLE, {
        x: x + 1.56, y: y + 0.47 + ii * 0.33, w: 0.32, h: 0.2,
        fill: { color: pri === "P0" ? "FEE2E2" : pri === "P1" ? "FEF3C7" : "F1F5F9" },
        line: { color: pri === "P0" ? "FCA5A5" : pri === "P1" ? C.amberLight : "CBD5E1" }
      });
      slide.addText(pri, {
        x: x + 1.56, y: y + 0.47 + ii * 0.33, w: 0.32, h: 0.2,
        fontSize: 8.5, bold: true, color: priColor, align: "center", valign: "middle", margin: 0
      });
      slide.addText(desc, {
        x: x + 1.96, y: y + 0.44 + ii * 0.33, w: 2.66, h: 0.28,
        fontSize: 9.5, color: C.text2, margin: 0
      });
    });
  });
}

// ========================================================================
// Slide 6 — 用户操作流程
// ========================================================================
{
  const slide = pres.addSlide();
  slide.background = { color: C.bg };
  addNav(slide, 3);
  addSectionTitle(slide, 0.38, 0.62, "用户操作流程", "生成脚本的核心交互路径（3步完成）");

  const steps = [
    { num: "1", title: "选择产品", icon: "🛒", details: ["搜索/筛选产品", "按品类过滤", "查看卖点摘要", "点击选中产品"] },
    { num: "2", title: "配置参数", icon: "⚙️", details: ["选择视频类型（9种）", "品类智能推荐类型★", "选择生成引擎", "（可选）填写额外要求"] },
    { num: "3", title: "生成脚本", icon: "✨", details: ["AI分析卖点+模板", "检索相似爆款参考", "生成带时间标注脚本", "展示分段结构"] },
    { num: "4", title: "使用输出", icon: "📋", details: ["一键复制脚本", "输入优化意见重生成", "存入爆款模板库", "查看历史记录"] },
  ];

  const boxY = 1.38;
  const boxH = 3.4;
  const boxW = 2.2;
  const gap = 0.14;

  steps.forEach((step, i) => {
    const x = 0.38 + i * (boxW + gap);
    addCard(slide, x, boxY, boxW, boxH, { fill: i === 2 ? "FFF8EE" : C.card });
    if (i === 2) {
      slide.addShape(pres.shapes.RECTANGLE, {
        x, y: boxY, w: boxW, h: 0.08,
        fill: { color: C.amber }, line: { color: C.amber }
      });
    }
    // 步骤圆圈
    slide.addShape(pres.shapes.OVAL, {
      x: x + 0.78, y: boxY + 0.2, w: 0.64, h: 0.64,
      fill: { color: i === 2 ? C.amber : "F3E8D0" }, line: { color: C.amber }
    });
    slide.addText(step.num, {
      x: x + 0.78, y: boxY + 0.2, w: 0.64, h: 0.64,
      fontSize: 18, bold: true, color: i === 2 ? C.white : C.amber,
      align: "center", valign: "middle", margin: 0
    });
    slide.addText(step.icon, {
      x: x + 0.6, y: boxY + 0.96, w: 1, h: 0.44,
      fontSize: 28, align: "center", margin: 0
    });
    slide.addText(step.title, {
      x: x + 0.18, y: boxY + 1.44, w: boxW - 0.36, h: 0.32,
      fontSize: 14, bold: true, color: C.dark, align: "center", margin: 0
    });
    step.details.forEach((d, di) => {
      slide.addShape(pres.shapes.OVAL, {
        x: x + 0.28, y: boxY + 1.88 + di * 0.32, w: 0.1, h: 0.1,
        fill: { color: i === 2 ? C.amber : C.border }, line: { color: i === 2 ? C.amber : C.border }
      });
      slide.addText(d, {
        x: x + 0.44, y: boxY + 1.84 + di * 0.32, w: boxW - 0.58, h: 0.28,
        fontSize: 10, color: C.slate, margin: 0
      });
    });
    // 箭头
    if (i < 3) {
      slide.addShape(pres.shapes.LINE, {
        x: x + boxW + 0.01, y: boxY + boxH / 2, w: gap, h: 0,
        line: { color: C.amber, width: 2 }
      });
    }
  });

  // 底部辅助流程说明
  addCard(slide, 0.38, 4.92, 9.24, 0.52, { shadow: false });
  slide.addText("💡  改写模式：输入任意脚本 → 选择目标产品 → AI保留原有结构改写为法采版本  /  离线模式：未配置 API Key 时自动切换为法采本地模板引擎", {
    x: 0.55, y: 4.96, w: 8.9, h: 0.4,
    fontSize: 10, color: C.text2, margin: 0
  });
}

// ========================================================================
// Slide 7 — 系统架构
// ========================================================================
{
  const slide = pres.addSlide();
  slide.background = { color: C.bg };
  addNav(slide, 4);
  addSectionTitle(slide, 0.38, 0.62, "系统架构", "三层架构 · 双引擎设计 · 向量检索增强");

  // 三层框架
  const layers = [
    { label: "前端展示层", color: "EFF6FF", border: "93C5FD", textColor: "1D4ED8", items: ["Jinja2 模板渲染", "Tailwind CSS + 原生JS", "6个功能页面", "LocalHost / 局域网访问"] },
    { label: "业务逻辑层", color: "FFF8EE", border: C.amber, textColor: C.warm1, items: ["FastAPI 路由（5个router）", "ScriptGenerator（脚本引擎）", "ScriptRewriter（改写引擎）", "ChromaDB 向量检索"] },
    { label: "数据存储层", color: "F0FDF4", border: "6EE7B7", textColor: "065F46", items: ["SQLite（主数据库）", "ChromaDB（向量库）", "BAAI/bge-small-zh 向量模型", "Excel/CSV 导入通道"] },
  ];

  layers.forEach((layer, i) => {
    addCard(slide, 0.35 + i * 3.18, 1.3, 2.98, 3.1, { fill: layer.color, border: layer.border, shadow: true });
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 0.35 + i * 3.18, y: 1.3, w: 2.98, h: 0.4,
      fill: { color: layer.border }, line: { color: layer.border }
    });
    slide.addText(layer.label, {
      x: 0.35 + i * 3.18, y: 1.3, w: 2.98, h: 0.4,
      fontSize: 12, bold: true, color: C.white, align: "center", valign: "middle", margin: 0
    });
    layer.items.forEach((item, ii) => {
      slide.addShape(pres.shapes.OVAL, {
        x: 0.52 + i * 3.18, y: 1.88 + ii * 0.54, w: 0.12, h: 0.12,
        fill: { color: layer.border }, line: { color: layer.border }
      });
      slide.addText(item, {
        x: 0.7 + i * 3.18, y: 1.84 + ii * 0.54, w: 2.45, h: 0.28,
        fontSize: 10.5, color: layer.textColor === "1D4ED8" ? C.slate : layer.textColor, margin: 0
      });
    });
  });

  // 双引擎说明
  addCard(slide, 0.35, 4.52, 9.26, 0.82);
  slide.addText("双引擎降级策略", {
    x: 0.55, y: 4.58, w: 2, h: 0.28,
    fontSize: 11, bold: true, color: C.amber, margin: 0
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.55, y: 4.9, w: 1.9, h: 0.24,
    fill: { color: "DCFCE7" }, line: { color: "86EFAC" }
  });
  slide.addText("AI模式（DeepSeek）", {
    x: 0.55, y: 4.9, w: 1.9, h: 0.24,
    fontSize: 9.5, color: "166534", align: "center", valign: "middle", margin: 0
  });
  slide.addShape(pres.shapes.LINE, {
    x: 2.52, y: 5.02, w: 0.35, h: 0,
    line: { color: C.text2, width: 1.5 }
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 2.92, y: 4.9, w: 2.0, h: 0.24,
    fill: { color: "FEF3C7" }, line: { color: C.amberLight }
  });
  slide.addText("降级到法采模板引擎", {
    x: 2.92, y: 4.9, w: 2.0, h: 0.24,
    fontSize: 9.5, color: C.warm2, align: "center", valign: "middle", margin: 0
  });
  slide.addText("当 DEEPSEEK_API_KEY 未配置或API调用失败时自动降级，保障系统可用性，模板引擎内置法采专属话术库，支持多变体随机输出。", {
    x: 5.2, y: 4.56, w: 4.2, h: 0.7,
    fontSize: 9.5, color: C.text2, margin: 0
  });
}

// ========================================================================
// Slide 8 — 数据模型
// ========================================================================
{
  const slide = pres.addSlide();
  slide.background = { color: C.bg };
  addNav(slide, 5);
  addSectionTitle(slide, 0.38, 0.62, "数据模型", "六张核心数据表设计（SQLite）");

  const tables = [
    {
      name: "products", label: "产品表", color: "0369A1",
      fields: ["id (PK)", "name", "category", "price", "original_price", "commission_rate", "brand", "description", "status"]
    },
    {
      name: "selling_points", label: "卖点话术表", color: "7C3AED",
      fields: ["id (PK)", "product_id (FK→products)", "point_type", "content", "priority"]
    },
    {
      name: "script_templates", label: "脚本模板表", color: C.warm2,
      fields: ["id (PK)", "name", "video_type", "structure (JSON)", "hook_templates", "cta_templates", "duration_range", "example_script"]
    },
    {
      name: "viral_scripts", label: "爆款脚本库", color: "DC2626",
      fields: ["id (PK)", "category", "video_type", "title", "script_content", "performance_data", "embedding_id", "is_high_conversion"]
    },
    {
      name: "generated_scripts", label: "生成记录表", color: "059669",
      fields: ["id (PK)", "product_id (FK)", "template_id (FK)", "script_content", "video_type", "ai_model", "is_high_conversion", "created_at"]
    },
    {
      name: "reference_scripts", label: "参考脚本库", color: "0891B2",
      fields: ["id (PK)", "title", "video_url", "script_content", "video_type", "tags", "notes", "embedding_id"]
    },
  ];

  tables.forEach((tbl, i) => {
    const col = i % 3;
    const row = Math.floor(i / 3);
    const x = 0.28 + col * 3.25;
    const y = 1.28 + row * 2.12;
    addCard(slide, x, y, 3.0, 1.94);
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 3.0, h: 0.38,
      fill: { color: tbl.color }, line: { color: tbl.color }
    });
    slide.addText(`${tbl.name}`, {
      x: x + 0.1, y, w: 2.4, h: 0.38,
      fontSize: 10, bold: true, color: C.white, fontFace: "Consolas", valign: "middle", margin: 0
    });
    slide.addText(tbl.label, {
      x: x + 0.1, y: y + 0.42, w: 2.8, h: 0.26,
      fontSize: 9.5, bold: true, color: tbl.color, margin: 0
    });
    tbl.fields.slice(0, 6).forEach((field, fi) => {
      slide.addText(`· ${field}`, {
        x: x + 0.14, y: y + 0.7 + fi * 0.2, w: 2.74, h: 0.2,
        fontSize: 9, color: C.slate, fontFace: "Consolas", margin: 0
      });
    });
    if (tbl.fields.length > 6) {
      slide.addText(`+${tbl.fields.length - 6} 更多字段`, {
        x: x + 0.14, y: y + 1.72, w: 2.74, h: 0.18,
        fontSize: 8.5, color: C.text2, margin: 0
      });
    }
  });
}

// ========================================================================
// Slide 9 — API接口
// ========================================================================
{
  const slide = pres.addSlide();
  slide.background = { color: C.bg };
  addNav(slide, 6);
  addSectionTitle(slide, 0.38, 0.62, "API 接口规范", "RESTful · 5个路由模块 · 共16个接口");

  const apis = [
    { prefix: "/api/scripts", tag: "脚本生成", color: "059669", methods: [
      ["POST", "/generate", "生成带货脚本（核心接口）"],
      ["POST", "/rewrite", "改写脚本为目标产品版本"],
      ["GET",  "/history", "获取生成历史记录（分页）"],
      ["POST", "/history/{id}/save-to-library", "保存到爆款库"],
      ["POST", "/history/{id}/toggle-high", "切换高成交标记"],
    ]},
    { prefix: "/api/products", tag: "产品管理", color: "0369A1", methods: [
      ["GET",    "/",            "获取产品列表（支持搜索/品类过滤）"],
      ["POST",   "/",            "新增产品"],
      ["GET",    "/categories",  "获取所有品类"],
      ["GET",    "/{id}",        "获取单个产品详情"],
      ["PUT",    "/{id}",        "更新产品信息"],
    ]},
    { prefix: "/api/templates", tag: "模板管理", color: "7C3AED", methods: [
      ["GET",  "/",        "获取脚本模板列表"],
      ["GET",  "/{id}",   "获取模板详情"],
    ]},
    { prefix: "/api/reference", tag: "参考脚本", color: "0891B2", methods: [
      ["GET",  "/",       "获取参考脚本库"],
      ["POST", "/",       "添加参考脚本"],
    ]},
    { prefix: "/api/import", tag: "数据导入", color: C.warm2, methods: [
      ["POST", "/products", "CSV/Excel批量导入产品数据"],
    ]},
  ];

  apis.forEach((api, i) => {
    const col = i < 2 ? i : (i < 4 ? i - 2 : 2);
    const row = i < 2 ? 0 : (i < 4 ? 1 : 1);
    const x = i < 2 ? 0.3 + i * 4.72 : (i < 4 ? 0.3 + (i - 2) * 4.72 : 5.12);
    const y = i < 2 ? 1.3 : 3.3;
    const cardH = i < 2 ? 1.86 : (i === 4 ? 0.72 : 1.86);
    addCard(slide, x, y, i < 2 ? 4.56 : (i === 4 ? 4.56 : 4.56), cardH);
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y, w: i < 2 ? 4.56 : 4.56, h: 0.3,
      fill: { color: api.color }, line: { color: api.color }
    });
    slide.addText(`${api.prefix}  (${api.tag})`, {
      x: x + 0.12, y, w: (i < 2 ? 4.56 : 4.56) - 0.24, h: 0.3,
      fontSize: 10, bold: true, color: C.white, fontFace: "Consolas", valign: "middle", margin: 0
    });
    api.methods.forEach((m, mi) => {
      const [method, path, desc] = m;
      const mc = method === "GET" ? "0369A1" : method === "POST" ? "059669" : method === "PUT" ? "7C3AED" : "DC2626";
      slide.addShape(pres.shapes.RECTANGLE, {
        x: x + 0.12, y: y + 0.38 + mi * 0.3, w: 0.52, h: 0.22,
        fill: { color: method === "GET" ? "DBEAFE" : method === "POST" ? "DCFCE7" : "EDE9FE" },
        line: { color: method === "GET" ? "93C5FD" : method === "POST" ? "6EE7B7" : "C4B5FD" }
      });
      slide.addText(method, {
        x: x + 0.12, y: y + 0.38 + mi * 0.3, w: 0.52, h: 0.22,
        fontSize: 8, bold: true, color: mc, align: "center", valign: "middle", margin: 0
      });
      slide.addText(path, {
        x: x + 0.7, y: y + 0.38 + mi * 0.3, w: 1.4, h: 0.22,
        fontSize: 9, color: C.dark, fontFace: "Consolas", valign: "middle", margin: 0
      });
      slide.addText(desc, {
        x: x + 2.14, y: y + 0.38 + mi * 0.3, w: (i < 2 ? 4.56 : 4.56) - 2.26, h: 0.22,
        fontSize: 9.5, color: C.text2, valign: "middle", margin: 0
      });
    });
  });
}

// ========================================================================
// Slide 10 — 部署说明
// ========================================================================
{
  const slide = pres.addSlide();
  slide.background = { color: C.bg };
  addNav(slide, 7);
  addSectionTitle(slide, 0.38, 0.62, "部署说明", "环境依赖 · 配置项 · 启动命令");

  // 依赖
  addCard(slide, 0.38, 1.3, 4.6, 1.5);
  slide.addText("技术依赖", {
    x: 0.56, y: 1.38, w: 4, h: 0.28,
    fontSize: 11, bold: true, color: C.amber, margin: 0
  });
  const deps = [
    ["Python", "3.12+"],
    ["FastAPI", "0.115.6"],
    ["SQLAlchemy", "2.0.36"],
    ["ChromaDB", "0.5.23"],
    ["OpenAI SDK", "1.57.4 (DeepSeek)"],
    ["Uvicorn", "0.34.0"],
  ];
  deps.forEach(([k, v], i) => {
    const col = i % 2;
    const row = Math.floor(i / 2);
    slide.addText(`${k}`, {
      x: 0.56 + col * 2.2, y: 1.72 + row * 0.28, w: 1.4, h: 0.24,
      fontSize: 10, bold: true, color: C.dark, fontFace: "Consolas", margin: 0
    });
    slide.addText(v, {
      x: 1.98 + col * 2.2, y: 1.72 + row * 0.28, w: 1.0, h: 0.24,
      fontSize: 10, color: C.text2, margin: 0
    });
  });

  // 环境变量
  addCard(slide, 0.38, 2.92, 4.6, 1.36);
  slide.addText("环境变量配置 (.env)", {
    x: 0.56, y: 3.0, w: 4.2, h: 0.28,
    fontSize: 11, bold: true, color: C.amber, margin: 0
  });
  const envs = [
    "DEEPSEEK_API_KEY=sk-xxxxxxxx",
    "DEEPSEEK_MODEL=deepseek-chat",
    "DATABASE_URL=sqlite:///./data/script_agent.db",
    "EMBEDDING_MODEL_NAME=BAAI/bge-small-zh-v1.5",
  ];
  envs.forEach((env, i) => {
    slide.addText(env, {
      x: 0.56, y: 3.34 + i * 0.24, w: 4.28, h: 0.22,
      fontSize: 9.5, color: C.warm1, fontFace: "Consolas", margin: 0
    });
  });

  // 启动方式
  addCard(slide, 5.18, 1.3, 4.44, 1.94);
  slide.addText("启动命令", {
    x: 5.36, y: 1.38, w: 4, h: 0.28,
    fontSize: 11, bold: true, color: C.amber, margin: 0
  });
  const cmds = [
    ["安装依赖", "pip install -r requirements.txt"],
    ["初始化数据", "python seed_all.py"],
    ["启动服务", "uvicorn main:app --host 0.0.0.0 --port 8000 --reload"],
    ["Windows快捷", "双击 run.bat  或  启动Agent.vbs"],
  ];
  cmds.forEach(([label, cmd], i) => {
    slide.addText(label, {
      x: 5.36, y: 1.72 + i * 0.38, w: 1.2, h: 0.28,
      fontSize: 9.5, bold: true, color: C.dark, margin: 0
    });
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 6.64, y: 1.74 + i * 0.38, w: 2.82, h: 0.24,
      fill: { color: "1E293B" }, line: { color: "334155" }
    });
    slide.addText(cmd, {
      x: 6.68, y: 1.74 + i * 0.38, w: 2.74, h: 0.24,
      fontSize: 8.5, color: "7DD3FC", fontFace: "Consolas", valign: "middle", margin: 0
    });
  });

  // 访问地址
  addCard(slide, 5.18, 3.36, 4.44, 0.92);
  slide.addText("访问地址", {
    x: 5.36, y: 3.44, w: 4.2, h: 0.28,
    fontSize: 11, bold: true, color: C.amber, margin: 0
  });
  [
    ["本机", "http://localhost:8000/app"],
    ["局域网", "http://<本机IP>:8000/app"],
  ].forEach(([t, url], i) => {
    slide.addText(t + "：", {
      x: 5.36, y: 3.78 + i * 0.28, w: 0.9, h: 0.24,
      fontSize: 10, bold: true, color: C.dark, margin: 0
    });
    slide.addText(url, {
      x: 6.28, y: 3.78 + i * 0.28, w: 3.22, h: 0.24,
      fontSize: 10, color: "0369A1", fontFace: "Consolas", margin: 0
    });
  });

  // 页面路由
  addCard(slide, 0.38, 4.38, 9.24, 0.96);
  slide.addText("页面路由", {
    x: 0.56, y: 4.44, w: 1.5, h: 0.28,
    fontSize: 11, bold: true, color: C.amber, margin: 0
  });
  const routes = [
    ["/app", "生成脚本"],
    ["/app/rewrite", "改写脚本"],
    ["/app/products", "产品管理"],
    ["/app/import", "数据导入"],
    ["/app/templates", "模板库"],
    ["/app/history", "历史记录"],
  ];
  routes.forEach(([path, name], i) => {
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 0.56 + i * 1.52, y: 4.76, w: 1.42, h: 0.46,
      fill: { color: i === 0 ? "FEF3C7" : "F8FAFC" },
      line: { color: i === 0 ? C.amberLight : C.border, width: 1 }
    });
    slide.addText(path, {
      x: 0.56 + i * 1.52, y: 4.76, w: 1.42, h: 0.24,
      fontSize: 9, color: "0369A1", fontFace: "Consolas", align: "center", valign: "middle", margin: 0
    });
    slide.addText(name, {
      x: 0.56 + i * 1.52, y: 5.0, w: 1.42, h: 0.22,
      fontSize: 9.5, color: C.dark, align: "center", valign: "middle", bold: true, margin: 0
    });
  });
}

// ========================================================================
// Slide 11 — 产品路线图
// ========================================================================
{
  const slide = pres.addSlide();
  slide.background = { color: C.bg };
  addNav(slide, 8);
  addSectionTitle(slide, 0.38, 0.62, "产品路线图", "已实现功能 · 后续迭代规划");

  // 已实现
  addCard(slide, 0.38, 1.3, 4.6, 3.7);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.38, y: 1.3, w: 4.6, h: 0.38,
    fill: { color: "059669" }, line: { color: "059669" }
  });
  slide.addText("✅  v1.0 已完成功能", {
    x: 0.54, y: 1.3, w: 4.28, h: 0.38,
    fontSize: 12, bold: true, color: C.white, valign: "middle", margin: 0
  });
  const done = [
    "核心脚本生成（DeepSeek AI + 模板引擎）",
    "57款法采产品数据入库及卖点管理",
    "9种视频类型 + 品类推荐映射",
    "向量检索相似爆款参考（ChromaDB）",
    "脚本改写功能（保留结构）",
    "生成历史记录与高成交标记",
    "爆款脚本库与参考脚本库",
    "CSV/Excel 批量产品导入",
    "局域网多端访问（手机可用）",
    "多变体随机生成（避免重复）",
    "按建议优化重生成",
    "Windows 一键启动（run.bat）",
  ];
  done.forEach((item, i) => {
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 0.56, y: 1.76 + i * 0.27, w: 0.2, h: 0.2,
      fill: { color: "DCFCE7" }, line: { color: "6EE7B7" }
    });
    slide.addText("✓", {
      x: 0.56, y: 1.76 + i * 0.27, w: 0.2, h: 0.2,
      fontSize: 8.5, bold: true, color: "059669", align: "center", valign: "middle", margin: 0
    });
    slide.addText(item, {
      x: 0.82, y: 1.74 + i * 0.27, w: 4.0, h: 0.24,
      fontSize: 10, color: C.dark, margin: 0
    });
  });

  // 待规划
  addCard(slide, 5.18, 1.3, 4.44, 3.7);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 5.18, y: 1.3, w: 4.44, h: 0.38,
    fill: { color: C.amber }, line: { color: C.amber }
  });
  slide.addText("🚀  后续迭代规划", {
    x: 5.34, y: 1.3, w: 4.12, h: 0.38,
    fontSize: 12, bold: true, color: C.white, valign: "middle", margin: 0
  });
  const roadmap = [
    ["v1.1", "短期", [
      "脚本质量评分（可读性/转化力评分）",
      "多产品批量生成（队列模式）",
      "脚本收藏夹与分类管理",
    ]],
    ["v1.2", "中期", [
      "接入巨量千川投放数据分析",
      "AI优化建议（基于跑量数据）",
      "脚本关键词高亮与镜头标注",
    ]],
    ["v2.0", "长期", [
      "多模型支持（GPT-4o / Qwen等）",
      "抖音爆款脚本自动同步入库",
      "团队协作与脚本审核工作流",
    ]],
  ];
  roadmap.forEach(([ver, phase, items], vi) => {
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 5.28, y: 1.76 + vi * 1.12, w: 0.5, h: 0.28,
      fill: { color: vi === 0 ? "059669" : vi === 1 ? C.amber : "7C3AED" },
      line: { color: vi === 0 ? "059669" : vi === 1 ? C.amber : "7C3AED" }
    });
    slide.addText(ver, {
      x: 5.28, y: 1.76 + vi * 1.12, w: 0.5, h: 0.28,
      fontSize: 9, bold: true, color: C.white, align: "center", valign: "middle", margin: 0
    });
    slide.addText(phase, {
      x: 5.84, y: 1.76 + vi * 1.12, w: 0.7, h: 0.28,
      fontSize: 9.5, color: C.text2, valign: "middle", margin: 0
    });
    items.forEach((item, ii) => {
      slide.addShape(pres.shapes.OVAL, {
        x: 5.34, y: 2.1 + vi * 1.12 + ii * 0.27, w: 0.1, h: 0.1,
        fill: { color: C.amberLight }, line: { color: C.amberLight }
      });
      slide.addText(item, {
        x: 5.5, y: 2.06 + vi * 1.12 + ii * 0.27, w: 4.04, h: 0.24,
        fontSize: 10, color: C.slate, margin: 0
      });
    });
  });

  // 底部
  addCard(slide, 0.38, 5.12, 9.24, 0.4, { shadow: false, fill: "FEF3C7", border: C.amberLight });
  slide.addText("🎯  当前重点：保障局域网稳定访问 → 补充更多产品卖点数据 → 接入千川投放数据实现闭环优化", {
    x: 0.55, y: 5.16, w: 8.9, h: 0.3,
    fontSize: 10, color: C.warm1, margin: 0, bold: true
  });
}

// ========================================================================
// Slide 12 — 结束页
// ========================================================================
{
  const slide = pres.addSlide();
  slide.background = { color: C.headerBg };

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 2.4, w: 10, h: 0.08,
    fill: { color: C.amber }, line: { color: C.amber }
  });

  slide.addText("🍞", {
    x: 0, y: 0.6, w: 10, h: 1.2,
    fontSize: 72, align: "center", margin: 0
  });
  slide.addText("法采新媒体运营 Agent", {
    x: 0, y: 1.8, w: 10, h: 0.6,
    fontSize: 28, bold: true, color: C.white, align: "center", margin: 0
  });
  slide.addText("抖音短视频带货脚本智能生成系统", {
    x: 0, y: 2.54, w: 10, h: 0.38,
    fontSize: 14, color: "D5C4A1", align: "center", margin: 0
  });
  slide.addText("v1.0.0 · 2026-05 · 法采运营团队", {
    x: 0, y: 3.04, w: 10, h: 0.32,
    fontSize: 11, color: "8B6543", align: "center", margin: 0
  });

  const summary = ["57 款产品", "9 种视频类型", "双引擎生成", "向量检索增强", "局域网多端"];
  summary.forEach((item, i) => {
    addCard(slide, 0.68 + i * 1.74, 3.58, 1.54, 0.7, { fill: "4A2408", border: "6B3A1A" });
    slide.addText(item, {
      x: 0.68 + i * 1.74, y: 3.58, w: 1.54, h: 0.7,
      fontSize: 10.5, bold: true, color: C.amber, align: "center", valign: "middle", margin: 0
    });
  });

  slide.addText("localhost:8000/app", {
    x: 0, y: 4.52, w: 10, h: 0.3,
    fontSize: 12, color: "7DD3FC", align: "center", fontFace: "Consolas", margin: 0
  });
}

// ========== 写出文件 ==========
const outPath = "C:/Users/Probably/WorkBuddy/2026-05-07-task-2/法采新媒体运营Agent_PRD.pptx";
pres.writeFile({ fileName: outPath })
  .then(() => console.log("✅ PRD生成成功：" + outPath))
  .catch(e => { console.error("❌ 生成失败：", e); process.exit(1); });
