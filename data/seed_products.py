"""法采产品数据库 — 全系列在售产品"""
from database import SessionLocal
from models import Product, SellingPoint


FAICAI_PRODUCTS = []

# =========================================================
# 一、调色系列
# =========================================================
FAICAI_PRODUCTS += [
    {
        "name": "水性色素（胶状）",
        "category": "烘焙调色",
        "price": 12.0,
        "original_price": 22.0,
        "commission_rate": 25.0,
        "brand": "法采",
        "description": "胶状水性色素，浓稠度高，易上色不花，适合奶油、翻糖、马卡龙调色",
        "selling_points": [
            {"point_type": "功效", "content": "胶状质地浓稠度高，一点点就上色，不稀释奶油", "priority": 1},
            {"point_type": "性价比", "content": "一小瓶能用几十次，比进口色素便宜一半", "priority": 2},
            {"point_type": "场景", "content": "奶油调色、翻糖上色、马卡龙壳染色一瓶搞定", "priority": 3},
            {"point_type": "痛点", "content": "水性配方不油不腻，洗完手不留色", "priority": 4},
        ]
    },
    {
        "name": "油性色素",
        "category": "烘焙调色",
        "price": 15.0,
        "original_price": 28.0,
        "commission_rate": 25.0,
        "brand": "法采",
        "description": "油性色素，专为巧克力、奶油霜等油脂类原料设计，着色均匀不分离",
        "selling_points": [
            {"point_type": "功效", "content": "专为巧克力/奶油霜研发，油性基底完美融合不分离", "priority": 1},
            {"point_type": "性价比", "content": "一滴就能染一盆巧克力，用量超级省", "priority": 2},
            {"point_type": "场景", "content": "巧克力调色、甘纳许染色、淋面蛋糕必备", "priority": 3},
        ]
    },
    {
        "name": "果蔬色素",
        "category": "烘焙调色",
        "price": 16.0,
        "original_price": 30.0,
        "commission_rate": 25.0,
        "brand": "法采",
        "description": "天然果蔬提取色素，健康安全，适合追求天然配色的烘焙爱好者",
        "selling_points": [
            {"point_type": "功效", "content": "天然果蔬提取，给宝宝做蛋糕也放心", "priority": 1},
            {"point_type": "对比", "content": "比合成色素贵一点但放心一百倍，宝妈首选", "priority": 2},
            {"point_type": "场景", "content": "儿童蛋糕、健康烘焙、私房接单必备卖点", "priority": 3},
        ]
    },
    {
        "name": "高浓果蔬色素",
        "category": "烘焙调色",
        "price": 22.0,
        "original_price": 42.0,
        "commission_rate": 25.0,
        "brand": "法采",
        "description": "高浓度果蔬色素，浓缩配方用量更省，色彩更鲜艳持久",
        "selling_points": [
            {"point_type": "功效", "content": "比普通果蔬色素浓3倍，同样价格颜色更艳", "priority": 1},
            {"point_type": "性价比", "content": "高浓缩配方，一瓶抵普通3瓶", "priority": 2},
            {"point_type": "场景", "content": "需要鲜艳颜色的韩式裱花、马卡龙必备", "priority": 3},
        ]
    },
    {
        "name": "水状色素",
        "category": "烘焙调色",
        "price": 8.0,
        "original_price": 15.0,
        "commission_rate": 25.0,
        "brand": "法采",
        "description": "水状稀薄色素，适合大面积喷色和浸染，流动性好",
        "selling_points": [
            {"point_type": "功效", "content": "流动性强，适合喷枪大面积喷色，省时省力", "priority": 1},
            {"point_type": "性价比", "content": "一支8块，新手入门首选，多色随便买", "priority": 2},
            {"point_type": "场景", "content": "喷色蛋糕、渐变染色、浸染翻糖花瓣", "priority": 3},
        ]
    },
    {
        "name": "色素笔",
        "category": "烘焙调色",
        "price": 18.0,
        "original_price": 35.0,
        "commission_rate": 25.0,
        "brand": "法采",
        "description": "可食用色素笔，直接在翻糖/奶油上绘画写字，多色可选",
        "selling_points": [
            {"point_type": "功效", "content": "翻糖上直接画画写字，手残党也能做精致蛋糕", "priority": 1},
            {"point_type": "场景", "content": "糖牌写字、翻糖人偶五官、饼干装饰一笔搞定", "priority": 2},
            {"point_type": "痛点", "content": "不用调色素不用买画笔，打开直接画，太省事了", "priority": 3},
        ]
    },
    {
        "name": "水溶色粉",
        "category": "烘焙调色",
        "price": 10.0,
        "original_price": 20.0,
        "commission_rate": 25.0,
        "brand": "法采",
        "description": "水溶性色粉，粉质细腻易溶解，适合蛋白霜/糖霜/面团调色",
        "selling_points": [
            {"point_type": "功效", "content": "粉质超细遇水即溶，调蛋白霜不结块不消泡", "priority": 1},
            {"point_type": "性价比", "content": "一小瓶染几十次，比液体色素更耐用", "priority": 2},
            {"point_type": "场景", "content": "蛋白糖、糖霜饼干、彩色面团通吃", "priority": 3},
        ]
    },
    {
        "name": "油溶色粉",
        "category": "烘焙调色",
        "price": 12.0,
        "original_price": 22.0,
        "commission_rate": 25.0,
        "brand": "法采",
        "description": "油溶性色粉，专为巧克力/可可脂等油脂类食材调色设计",
        "selling_points": [
            {"point_type": "功效", "content": "油溶配方，调巧克力不结粒、不返砂", "priority": 1},
            {"point_type": "场景", "content": "巧克力插件、星空淋面、彩色可可脂必备", "priority": 2},
        ]
    },
    {
        "name": "色粉盘",
        "category": "烘焙调色",
        "price": 28.0,
        "original_price": 55.0,
        "commission_rate": 25.0,
        "brand": "法采",
        "description": "多色色粉组合盘，一套搞定常用色彩，自带收纳盒",
        "selling_points": [
            {"point_type": "性价比", "content": "一套12色只要28，单独买要上百，省大发了", "priority": 1},
            {"point_type": "场景", "content": "新手入门套装，什么颜色都有不用纠结买哪个", "priority": 2},
            {"point_type": "痛点", "content": "自带收纳盒，色粉不再撒得到处都是", "priority": 3},
        ]
    },
    {
        "name": "竹炭粉",
        "category": "烘焙调色",
        "price": 9.0,
        "original_price": 18.0,
        "commission_rate": 25.0,
        "brand": "法采",
        "description": "天然竹炭粉，纯黑色天然调色，做暗黑系蛋糕/竹炭面包必备",
        "selling_points": [
            {"point_type": "功效", "content": "天然竹炭研磨，做黑色蛋糕不用合成色素", "priority": 1},
            {"point_type": "场景", "content": "暗黑系蛋糕、竹炭面包、黑色马卡龙壳专用", "priority": 2},
        ]
    },
    {
        "name": "果蔬粉（综合系列）",
        "category": "烘焙调色",
        "price": 9.9,
        "original_price": 20.0,
        "commission_rate": 25.0,
        "brand": "法采",
        "description": "涵盖紫薯、南瓜、红曲米、抹茶、菠菜、可可、芒果、红甜菜、草莓、火龙果、斑斓、仙人掌等12种口味果蔬粉，天然食材研磨",
        "selling_points": [
            {"point_type": "功效", "content": "12种口味任选，纯天然果蔬研磨，调色+调味二合一", "priority": 1},
            {"point_type": "性价比", "content": "9.9一袋，买5送1，集齐全部口味不心疼", "priority": 2},
            {"point_type": "场景", "content": "彩色馒头、果蔬面条、彩虹蛋糕、宝宝辅食全能用", "priority": 3},
            {"point_type": "痛点", "content": "不用自己磨果蔬汁了，直接用粉方便100倍", "priority": 4},
        ]
    },
    {
        "name": "藻蓝蛋白粉",
        "category": "烘焙调色",
        "price": 35.0,
        "original_price": 68.0,
        "commission_rate": 20.0,
        "brand": "法采",
        "description": "天然藻蓝蛋白提取，梦幻蓝色，高颜值烘焙专用天然色素",
        "selling_points": [
            {"point_type": "功效", "content": "自然界少有的天然蓝色素，做蓝色蛋糕再也不用合成色素", "priority": 1},
            {"point_type": "场景", "content": "海洋风蛋糕、蓝色马卡龙、星空主题甜品必备", "priority": 2},
        ]
    },
    {
        "name": "墨鱼汁粉",
        "category": "烘焙调色",
        "price": 25.0,
        "original_price": 48.0,
        "commission_rate": 20.0,
        "brand": "法采",
        "description": "天然墨鱼汁提取粉末，纯正黑色天然染色，做墨鱼面包/黑色意面",
        "selling_points": [
            {"point_type": "功效", "content": "纯天然墨鱼汁粉，比竹炭粉还黑还纯正", "priority": 1},
            {"point_type": "场景", "content": "墨鱼面包、黑色意面、暗黑系甜品专用天然黑", "priority": 2},
        ]
    },
    {
        "name": "红曲粉",
        "category": "烘焙调色",
        "price": 8.0,
        "original_price": 15.0,
        "commission_rate": 25.0,
        "brand": "法采",
        "description": "传统红曲米粉，天然红色染色，做红丝绒蛋糕/叉烧肉必备",
        "selling_points": [
            {"point_type": "功效", "content": "千年传统天然红曲，做红色蛋糕最自然的颜色", "priority": 1},
            {"point_type": "场景", "content": "红丝绒蛋糕、红曲馒头、中式点心专用", "priority": 2},
        ]
    },
]

# =========================================================
# 二、装饰系列
# =========================================================
FAICAI_PRODUCTS += [
    {
        "name": "防潮翻糖膏（白色/彩色/果味）",
        "category": "烘焙装饰",
        "price": 25.0,
        "original_price": 48.0,
        "commission_rate": 22.0,
        "brand": "法采",
        "description": "防潮配方翻糖膏，白色/多色/果味可选，柔软易擀不开裂，铺面/捏花通用",
        "selling_points": [
            {"point_type": "功效", "content": "防潮配方不易受潮变软，南方回南天也扛得住", "priority": 1},
            {"point_type": "性价比", "content": "一包能做3-4个6寸铺面，比进口翻糖省一半", "priority": 2},
            {"point_type": "场景", "content": "蛋糕铺面、捏花、人偶、糖牌都能用，一膏多用", "priority": 3},
            {"point_type": "痛点", "content": "柔软好擀不费力，新手也能擀出光滑铺面", "priority": 4},
        ]
    },
    {
        "name": "防潮干佩斯（通用型/柔软型/蝴蝶结型/糖牌型/人偶型）",
        "category": "烘焙装饰",
        "price": 22.0,
        "original_price": 45.0,
        "commission_rate": 22.0,
        "brand": "法采",
        "description": "5种细分干佩斯：通用捏花、柔软铺面、蝴蝶结专用、糖牌专用、人偶专用，按需选择",
        "selling_points": [
            {"point_type": "功效", "content": "5种专业细分，做什么选什么，不将就", "priority": 1},
            {"point_type": "性价比", "content": "专业级干佩斯，价格只要进口的1/3", "priority": 2},
            {"point_type": "场景", "content": "蝴蝶结不塌、人偶不裂、糖牌硬挺，专款专用效果好", "priority": 3},
        ]
    },
    {
        "name": "彩色防潮翻糖片",
        "category": "烘焙装饰",
        "price": 18.0,
        "original_price": 35.0,
        "commission_rate": 22.0,
        "brand": "法采",
        "description": "预调色翻糖片，直接擀开使用，省去调色步骤，多色可选",
        "selling_points": [
            {"point_type": "功效", "content": "已经调好色了，拆开直接擀直接铺，省去调色时间", "priority": 1},
            {"point_type": "痛点", "content": "不用自己揉色素揉到手酸，懒人烘焙必备", "priority": 2},
        ]
    },
    {
        "name": "糖珠（经典白珠金珠系列）",
        "category": "烘焙装饰",
        "price": 6.0,
        "original_price": 12.0,
        "commission_rate": 25.0,
        "brand": "法采",
        "description": "经典白色/金色糖珠，蛋糕装饰基础款，百搭不挑风格",
        "selling_points": [
            {"point_type": "功效", "content": "经典白金色系，什么蛋糕撒上都好看，百搭之王", "priority": 1},
            {"point_type": "性价比", "content": "6块钱一瓶，随便撒不心疼", "priority": 2},
        ]
    },
    {
        "name": "糖珠（幻彩系列）",
        "category": "烘焙装饰",
        "price": 8.0,
        "original_price": 16.0,
        "commission_rate": 25.0,
        "brand": "法采",
        "description": "幻彩变色糖珠，不同角度呈现不同色彩，高颜值蛋糕必备",
        "selling_points": [
            {"point_type": "功效", "content": "光线不同角度颜色不同，蛋糕瞬间变高级", "priority": 1},
            {"point_type": "场景", "content": "婚礼蛋糕、宝宝宴、生日蛋糕颜值加分利器", "priority": 2},
        ]
    },
    {
        "name": "糖珠（韩风潮流系列）",
        "category": "烘焙装饰",
        "price": 9.0,
        "original_price": 18.0,
        "commission_rate": 25.0,
        "brand": "法采",
        "description": "韩式ins风糖珠系列，多款流行配色，做韩式简约蛋糕专用",
        "selling_points": [
            {"point_type": "功效", "content": "韩式ins风配色，抹茶绿、奶茶棕、莫兰迪色系全有", "priority": 1},
            {"point_type": "场景", "content": "韩式简约蛋糕装饰标配，拍出来就是小红书爆款", "priority": 2},
        ]
    },
    {
        "name": "糖珠（西班牙系列）",
        "category": "烘焙装饰",
        "price": 12.0,
        "original_price": 25.0,
        "commission_rate": 20.0,
        "brand": "法采",
        "description": "西班牙进口级品质糖珠，颗粒饱满均匀，色泽高级，高端烘焙专用",
        "selling_points": [
            {"point_type": "功效", "content": "西班牙进口品质，颗粒均匀饱满，肉眼可见的高级感", "priority": 1},
            {"point_type": "对比", "content": "和进口店卖30+的品质一模一样，价格只要三分之一", "priority": 2},
        ]
    },
    {
        "name": "拉线膏（12色）",
        "category": "烘焙装饰",
        "price": 15.0,
        "original_price": 28.0,
        "commission_rate": 22.0,
        "brand": "法采",
        "description": "12色拉线膏套装，流畅不断线，蛋糕写字/拉花/描边专用",
        "selling_points": [
            {"point_type": "功效", "content": "12色齐全，拉线流畅不断，写字画画想怎么拉都行", "priority": 1},
            {"point_type": "痛点", "content": "不用自己调甘纳许写字了，开盖直接用，省心省力", "priority": 2},
        ]
    },
    {
        "name": "手绘膏（奶黄/嫩粉/浅蓝/白色/正黑/正红等）",
        "category": "烘焙装饰",
        "price": 12.0,
        "original_price": 22.0,
        "commission_rate": 22.0,
        "brand": "法采",
        "description": "多色手绘膏，直接在蛋糕/翻糖上绘画，覆盖力强不晕染",
        "selling_points": [
            {"point_type": "功效", "content": "覆盖力超强，浅色底上画深色一笔就显，不晕不花", "priority": 1},
            {"point_type": "场景", "content": "手绘蛋糕、糖牌绘画、翻糖人偶表情一笔搞定", "priority": 2},
        ]
    },
    {
        "name": "海苔酥脆松",
        "category": "烘焙装饰",
        "price": 18.0,
        "original_price": 35.0,
        "commission_rate": 20.0,
        "brand": "法采",
        "description": "海苔酥脆松，蛋糕肉松小贝专用，酥脆咸香不油腻",
        "selling_points": [
            {"point_type": "功效", "content": "酥脆不油腻，裹在蛋糕上嘎嘣脆，咸甜搭配绝了", "priority": 1},
            {"point_type": "场景", "content": "肉松小贝、肉松蛋糕卷、网红爆款必备原料", "priority": 2},
        ]
    },
    {
        "name": "金丝肉丝松",
        "category": "烘焙装饰",
        "price": 20.0,
        "original_price": 38.0,
        "commission_rate": 20.0,
        "brand": "法采",
        "description": "金丝肉丝松，拉丝效果好，金黄色泽，做网红肉松蛋糕必备",
        "selling_points": [
            {"point_type": "功效", "content": "金黄色泽+丝状拉丝效果，做出来的蛋糕颜值拉满", "priority": 1},
            {"point_type": "场景", "content": "网红拔丝蛋糕、金丝肉松面包、高颜值肉松小贝", "priority": 2},
        ]
    },
    {
        "name": "豆沙奶油霜",
        "category": "烘焙装饰",
        "price": 15.0,
        "original_price": 28.0,
        "commission_rate": 22.0,
        "brand": "法采",
        "description": "豆沙奶油霜，韩式裱花专用，质地细腻顺滑，易造型不融化",
        "selling_points": [
            {"point_type": "功效", "content": "韩式裱花专用豆沙霜，比纯奶油霜更稳定不化", "priority": 1},
            {"point_type": "场景", "content": "韩式裱花蛋糕、豆沙裱花课、私房接单利器", "priority": 2},
        ]
    },
]

# =========================================================
# 三、调味系列
# =========================================================
FAICAI_PRODUCTS += [
    {
        "name": "西点奶油调味果酱（20余种口味）",
        "category": "烘焙调味",
        "price": 15.0,
        "original_price": 28.0,
        "commission_rate": 22.0,
        "brand": "法采",
        "description": "专为奶油调味的果酱，草莓/蓝莓/芒果/百香果等20余种口味，单一口味及复合口味可选",
        "selling_points": [
            {"point_type": "功效", "content": "专为奶油研发，混入奶油不分离不稀释，水果味超正", "priority": 1},
            {"point_type": "场景", "content": "草莓奶油/芒果奶油/百香果奶油…20多种口味做出差异化", "priority": 2},
            {"point_type": "性价比", "content": "一瓶调一盆奶油，比买进口果茸便宜多了", "priority": 3},
        ]
    },
    {
        "name": "奶油调味茶酱（金桂乌龙/伯爵红茶/春山龙井/抹茶/伯牙茉莉）",
        "category": "烘焙调味",
        "price": 18.0,
        "original_price": 35.0,
        "commission_rate": 22.0,
        "brand": "法采",
        "description": "茶味奶油专用调味酱，金桂乌龙、伯爵红茶、春山龙井、抹茶、伯牙茉莉5款茶香风味",
        "selling_points": [
            {"point_type": "功效", "content": "5款茶香风味，茶味浓郁不苦涩，做茶系蛋糕天花板", "priority": 1},
            {"point_type": "场景", "content": "伯爵红茶蛋糕/龙井千层/茉莉奶油，国风茶点必备", "priority": 2},
            {"point_type": "痛点", "content": "不用自己煮茶泡茶过滤了，直接拌入奶油就行", "priority": 3},
        ]
    },
    {
        "name": "开心果酱（95%/98%含量）",
        "category": "烘焙调味",
        "price": 68.0,
        "original_price": 128.0,
        "commission_rate": 18.0,
        "brand": "法采",
        "description": "高纯度开心果酱，95%和98%两种含量可选，纯正开心果味，绿色源自果仁本色",
        "selling_points": [
            {"point_type": "功效", "content": "95%/98%超高含量开心果酱，不是勾兑的那种香精味", "priority": 1},
            {"point_type": "性价比", "content": "进口品牌卖200+的同等品质，68直接拿", "priority": 2},
            {"point_type": "场景", "content": "开心果奶油/开心果巴斯克/开心果马卡龙，高端私房必备", "priority": 3},
        ]
    },
    {
        "name": "黑芝麻酱",
        "category": "烘焙调味",
        "price": 25.0,
        "original_price": 48.0,
        "commission_rate": 22.0,
        "brand": "法采",
        "description": "纯黑芝麻研磨芝麻酱，浓郁芝麻香，做黑芝麻蛋糕/汤圆/面包专用",
        "selling_points": [
            {"point_type": "功效", "content": "纯黑芝麻石磨研磨，香气浓郁到隔壁邻居都闻得到", "priority": 1},
            {"point_type": "场景", "content": "黑芝麻蛋糕/黑芝麻面包/黑芝麻汤圆，养生烘焙爆款", "priority": 2},
        ]
    },
    {
        "name": "焦糖酱",
        "category": "烘焙调味",
        "price": 16.0,
        "original_price": 30.0,
        "commission_rate": 22.0,
        "brand": "法采",
        "description": "经典焦糖酱，焦香浓郁，可调奶油/做夹心/淋面，烘焙百搭",
        "selling_points": [
            {"point_type": "功效", "content": "焦香浓郁不过甜，比自己做省事10倍", "priority": 1},
            {"point_type": "场景", "content": "焦糖奶油/焦糖拿铁/焦糖夹心/焦糖淋面，万能焦糖酱", "priority": 2},
        ]
    },
    {
        "name": "海盐焦糖酱",
        "category": "烘焙调味",
        "price": 18.0,
        "original_price": 35.0,
        "commission_rate": 22.0,
        "brand": "法采",
        "description": "海盐焦糖酱，甜咸交织，口感层次丰富，高级感焦糖风味",
        "selling_points": [
            {"point_type": "功效", "content": "海盐+焦糖的绝妙配比，甜咸交织高级感拉满", "priority": 1},
            {"point_type": "场景", "content": "海盐焦糖蛋糕/海盐焦糖马卡龙/焦糖海盐拿铁", "priority": 2},
        ]
    },
    {
        "name": "伯爵红茶粉",
        "category": "烘焙调味",
        "price": 12.0,
        "original_price": 22.0,
        "commission_rate": 25.0,
        "brand": "法采",
        "description": "伯爵红茶研磨细粉，佛手柑香气浓郁，做茶味蛋糕/曲奇专用",
        "selling_points": [
            {"point_type": "功效", "content": "细粉级研磨，混入面粉/奶油无颗粒感，佛手柑香超正", "priority": 1},
            {"point_type": "场景", "content": "伯爵红茶蛋糕/红茶曲奇/红茶奶油，经典永不过时", "priority": 2},
        ]
    },
    {
        "name": "龙井茶粉",
        "category": "烘焙调味",
        "price": 15.0,
        "original_price": 28.0,
        "commission_rate": 25.0,
        "brand": "法采",
        "description": "春山龙井研磨茶粉，清雅豆香，国风茶点必备原料",
        "selling_points": [
            {"point_type": "功效", "content": "真正的龙井茶研磨，清雅豆香，不是普通绿茶粉能比的", "priority": 1},
            {"point_type": "场景", "content": "龙井千层/龙井慕斯/龙井曲奇，国风茶点高端局", "priority": 2},
        ]
    },
    {
        "name": "茉莉绿茶粉",
        "category": "烘焙调味",
        "price": 12.0,
        "original_price": 22.0,
        "commission_rate": 25.0,
        "brand": "法采",
        "description": "茉莉花+绿茶研磨细粉，清新茉莉花香，做茉莉系甜品专用",
        "selling_points": [
            {"point_type": "功效", "content": "茉莉花+绿茶双拼研磨，花香茶香融合，清新脱俗", "priority": 1},
            {"point_type": "场景", "content": "茉莉千层/茉莉慕斯/茉莉奶油，小清新爆款", "priority": 2},
        ]
    },
    {
        "name": "薄荷味香精（调味糖浆）",
        "category": "烘焙调味",
        "price": 10.0,
        "original_price": 18.0,
        "commission_rate": 25.0,
        "brand": "法采",
        "description": "薄荷调味糖浆，清凉薄荷风味，做薄荷奶油/薄荷巧克力专用",
        "selling_points": [
            {"point_type": "功效", "content": "天然薄荷提取，清凉感恰到好处不刺激", "priority": 1},
            {"point_type": "场景", "content": "薄荷巧克力蛋糕/薄荷奶油/夏日限定甜品", "priority": 2},
        ]
    },
    {
        "name": "香草荚",
        "category": "烘焙调味",
        "price": 28.0,
        "original_price": 55.0,
        "commission_rate": 20.0,
        "brand": "法采",
        "description": "马达加斯加进口香草荚，每根15cm+，籽多饱满，香气纯正",
        "selling_points": [
            {"point_type": "功效", "content": "马达加斯加进口，籽多到肉眼可见，一根顶两根", "priority": 1},
            {"point_type": "性价比", "content": "进口品质国产价格，私房接单必备天然香草", "priority": 2},
        ]
    },
    {
        "name": "香草精（含籽/不含籽）",
        "category": "烘焙调味",
        "price": 16.0,
        "original_price": 30.0,
        "commission_rate": 25.0,
        "brand": "法采",
        "description": "纯天然香草提取液，含籽款肉眼可见香草籽，不含籽款清澈透明",
        "selling_points": [
            {"point_type": "功效", "content": "天然提取不是人工香精，含籽款能看见真香草籽", "priority": 1},
            {"point_type": "场景", "content": "替代香草荚的性价比之选，日常烘焙够用了", "priority": 2},
        ]
    },
    {
        "name": "杏仁粉",
        "category": "烘焙调味",
        "price": 22.0,
        "original_price": 42.0,
        "commission_rate": 20.0,
        "brand": "法采",
        "description": "超细杏仁粉，马卡龙专用级别，粉质细腻无颗粒",
        "selling_points": [
            {"point_type": "功效", "content": "马卡龙级别超细研磨，过筛不费力，壳子超光滑", "priority": 1},
            {"point_type": "场景", "content": "马卡龙/杏仁蛋糕/达克瓦兹/费南雪专用", "priority": 2},
        ]
    },
    {
        "name": "杏仁片",
        "category": "烘焙调味",
        "price": 15.0,
        "original_price": 28.0,
        "commission_rate": 22.0,
        "brand": "法采",
        "description": "美国大杏仁薄切片，烤后金黄酥脆，蛋糕表面装饰/烘焙配料",
        "selling_points": [
            {"point_type": "功效", "content": "美国大杏仁薄切，烤出来又香又脆，大小均匀", "priority": 1},
            {"point_type": "场景", "content": "杏仁瓦片/蛋糕表面装饰/面包配料，酥脆加倍", "priority": 2},
        ]
    },
    {
        "name": "抹茶粉",
        "category": "烘焙调味",
        "price": 25.0,
        "original_price": 48.0,
        "commission_rate": 22.0,
        "brand": "法采",
        "description": "日式抹茶粉，颜色翠绿，茶香浓郁，烘焙级品质",
        "selling_points": [
            {"point_type": "功效", "content": "颜色翠绿不黄，烤出来还是好看的抹茶绿", "priority": 1},
            {"point_type": "场景", "content": "抹茶千层/抹茶拿铁/抹茶曲奇/抹茶慕斯，万物皆可抹茶", "priority": 2},
        ]
    },
    {
        "name": "可可粉",
        "category": "烘焙调味",
        "price": 18.0,
        "original_price": 35.0,
        "commission_rate": 22.0,
        "brand": "法采",
        "description": "碱化可可粉，颜色深黑，可可味浓郁，烘焙专用级",
        "selling_points": [
            {"point_type": "功效", "content": "碱化工艺颜色深黑不发红，可可味浓郁不发苦", "priority": 1},
            {"point_type": "场景", "content": "巧克力蛋糕/可可面包/提拉米苏/可可奶油专用", "priority": 2},
        ]
    },
    {
        "name": "斑斓粉",
        "category": "烘焙调味",
        "price": 15.0,
        "original_price": 28.0,
        "commission_rate": 25.0,
        "brand": "法采",
        "description": "东南亚斑斓叶研磨粉，天然绿色+独特清香，做斑斓蛋糕/糯米糕",
        "selling_points": [
            {"point_type": "功效", "content": "天然翠绿+独特斑斓清香，东南亚风味烘焙的灵魂", "priority": 1},
            {"point_type": "场景", "content": "斑斓蛋糕/斑斓糯米糕/斑斓千层，异域风情爆款", "priority": 2},
        ]
    },
    {
        "name": "0卡糖粉",
        "category": "烘焙调味",
        "price": 28.0,
        "original_price": 55.0,
        "commission_rate": 20.0,
        "brand": "法采",
        "description": "0卡代糖糖粉，赤藓糖醇+甜菊糖配方，烘焙级细腻糖粉",
        "selling_points": [
            {"point_type": "功效", "content": "0卡0脂0糖，糖尿病人也能吃，做健康烘焙差异化利器", "priority": 1},
            {"point_type": "场景", "content": "生酮蛋糕/减脂甜品/控糖烘焙，抓住健康消费趋势", "priority": 2},
        ]
    },
]

# =========================================================
# 四、夹心系列
# =========================================================
FAICAI_PRODUCTS += [
    {
        "name": "巧克力夹心脆（代脂/纯脂，共17款口味）",
        "category": "烘焙夹心",
        "price": 22.0,
        "original_price": 42.0,
        "commission_rate": 22.0,
        "brand": "法采",
        "description": "17款口味巧克力夹心脆，代脂/纯脂可选，蛋糕夹层口感升级神器",
        "selling_points": [
            {"point_type": "功效", "content": "夹在蛋糕层里咬下去嘎嘣脆，口感层次瞬间拉满", "priority": 1},
            {"point_type": "场景", "content": "蛋糕夹层/慕斯夹心/雪媚娘内心，17种口味不重样", "priority": 2},
            {"point_type": "痛点", "content": "纯脂款入口即化，代脂款成本更低，按需选择", "priority": 3},
        ]
    },
    {
        "name": "黄油薄脆（基础款/浓香款）",
        "category": "烘焙夹心",
        "price": 12.0,
        "original_price": 22.0,
        "commission_rate": 25.0,
        "brand": "法采",
        "description": "黄油薄脆片，基础款和浓香款可选，蛋糕夹层/表面装饰专用",
        "selling_points": [
            {"point_type": "功效", "content": "超薄超脆，一口下去满满的黄油香，口感加分利器", "priority": 1},
            {"point_type": "场景", "content": "蛋糕夹层/奶油表面装饰/冰淇淋topping，万能薄脆", "priority": 2},
        ]
    },
    {
        "name": "巧克力纯脂脆珠",
        "category": "烘焙夹心",
        "price": 28.0,
        "original_price": 55.0,
        "commission_rate": 20.0,
        "brand": "法采",
        "description": "纯可可脂巧克力脆珠，一口爆浆，做蛋糕夹心/慕斯内心爆款",
        "selling_points": [
            {"point_type": "功效", "content": "咬开巧克力薄壳里面是脆脆的内心，一口口感爆炸", "priority": 1},
            {"point_type": "场景", "content": "网红爆浆蛋糕/慕斯夹心/雪媚娘内心，卖点满满", "priority": 2},
        ]
    },
    {
        "name": "奶冻粉（椰子/伯爵红茶/抹茶/芝士/拿铁/可可/芋泥/伯牙茉莉等）",
        "category": "烘焙夹心",
        "price": 15.0,
        "original_price": 28.0,
        "commission_rate": 22.0,
        "brand": "法采",
        "description": "8种口味奶冻预拌粉，加水/牛奶搅拌即可，蛋糕夹心奶冻专用",
        "selling_points": [
            {"point_type": "功效", "content": "8种口味随便选，加水/奶搅一搅冷藏就行，傻瓜式操作", "priority": 1},
            {"point_type": "场景", "content": "蛋糕夹心奶冻/杯子甜点/奶茶小料，网红甜品必备", "priority": 2},
            {"point_type": "痛点", "content": "不用自己调配吉利丁了，新手也能做出Q弹奶冻", "priority": 3},
        ]
    },
    {
        "name": "布蕾粉（焦糖味/抹茶味）",
        "category": "烘焙夹心",
        "price": 13.0,
        "original_price": 25.0,
        "commission_rate": 22.0,
        "brand": "法采",
        "description": "焦糖味和抹茶味布蕾预拌粉，法式烤布蕾/布蕾蛋糕夹心专用",
        "selling_points": [
            {"point_type": "功效", "content": "法式布蕾口感，烤出来表面焦脆内心嫩滑，高级感满分", "priority": 1},
            {"point_type": "场景", "content": "烤布蕾/布蕾蛋糕/布蕾千层，法式甜品入门神器", "priority": 2},
        ]
    },
    {
        "name": "慕斯粉（酸奶/蓝莓/巧克力口味）",
        "category": "烘焙夹心",
        "price": 16.0,
        "original_price": 30.0,
        "commission_rate": 22.0,
        "brand": "法采",
        "description": "3种口味慕斯预拌粉，酸奶/蓝莓/巧克力，加水搅拌冷藏即成慕斯",
        "selling_points": [
            {"point_type": "功效", "content": "3种经典口味，一包做出顺滑慕斯，夏天做慕斯蛋糕绝了", "priority": 1},
            {"point_type": "痛点", "content": "不用打发奶油不用调吉利丁，搅一搅冷藏就搞定", "priority": 2},
        ]
    },
    {
        "name": "栗子蓉（原味/甜味）",
        "category": "烘焙夹心",
        "price": 20.0,
        "original_price": 38.0,
        "commission_rate": 22.0,
        "brand": "法采",
        "description": "纯栗子研磨栗子蓉，原味和甜味可选，蒙布朗/栗子蛋糕专用",
        "selling_points": [
            {"point_type": "功效", "content": "纯栗子研磨不是勾兑的，吃得到栗子本身的香甜", "priority": 1},
            {"point_type": "场景", "content": "蒙布朗/栗子蛋糕/栗子千层，秋冬爆款专用栗子蓉", "priority": 2},
        ]
    },
    {
        "name": "蛋糕夹心冻（成品奶冻）",
        "category": "烘焙夹心",
        "price": 18.0,
        "original_price": 35.0,
        "commission_rate": 22.0,
        "brand": "法采",
        "description": "成品蛋糕夹心奶冻，开袋即用，直接夹入蛋糕层，省时省力",
        "selling_points": [
            {"point_type": "功效", "content": "开袋即用，直接往蛋糕层里一放，夹心搞定只需3秒", "priority": 1},
            {"point_type": "痛点", "content": "不用提前一天做奶冻了，急单也能加奶冻夹心", "priority": 2},
            {"point_type": "场景", "content": "私房接单急单救星，临时加夹心也不慌", "priority": 3},
        ]
    },
]

# =========================================================
# 五、刀叉配件系列
# =========================================================
FAICAI_PRODUCTS += [
    {
        "name": "0.7元袋装款（5叉5盘/5叉5盘1刀/10叉10盘1刀等规格，6款花色）",
        "category": "烘焙配件",
        "price": 0.7,
        "original_price": 1.5,
        "commission_rate": 15.0,
        "brand": "法采",
        "description": "经济实惠袋装刀叉盘套装，6款花色可选，含5叉5盘、5叉5盘1刀、10叉10盘1刀等规格",
        "selling_points": [
            {"point_type": "性价比", "content": "0.7元一套还带花色，成本几乎可以忽略", "priority": 1},
            {"point_type": "场景", "content": "蛋糕店/私房配送标配，买多了也不心疼", "priority": 2},
            {"point_type": "痛点", "content": "6种花色不会撞款，送礼蛋糕配不同花色显用心", "priority": 3},
        ]
    },
    {
        "name": "2元袋装款（5叉5盘/5叉5盘1刀等规格，4款花色）",
        "category": "烘焙配件",
        "price": 2.0,
        "original_price": 4.0,
        "commission_rate": 15.0,
        "brand": "法采",
        "description": "中端袋装刀叉盘套装，品质升级，4款花色，质感更好",
        "selling_points": [
            {"point_type": "功效", "content": "比0.7元款叉子更硬挺，齿更锋利，切蛋糕不费力", "priority": 1},
            {"point_type": "性价比", "content": "2元一套质感和进口品牌5元款不相上下", "priority": 2},
        ]
    },
    {
        "name": "2元盒装款（3件套/4件套/5件套，2款花色）",
        "category": "烘焙配件",
        "price": 2.0,
        "original_price": 4.0,
        "commission_rate": 15.0,
        "brand": "法采",
        "description": "盒装刀叉盘套装，送礼更有面子，3/4/5件套可选，2款花色",
        "selling_points": [
            {"point_type": "场景", "content": "盒装有档次，配生日蛋糕送人体面不丢面", "priority": 1},
            {"point_type": "性价比", "content": "盒子成本算进去才2块，外面单买盒子就要1块", "priority": 2},
        ]
    },
    {
        "name": "2.5元盒装款（6件套5人份/10人份，9款花色）",
        "category": "烘焙配件",
        "price": 2.5,
        "original_price": 5.0,
        "commission_rate": 15.0,
        "brand": "法采",
        "description": "高端盒装刀叉盘套装，6件套配置，5人份/10人份可选，9款花色任选",
        "selling_points": [
            {"point_type": "功效", "content": "9款花色全网最全，什么风格的蛋糕都能配上", "priority": 1},
            {"point_type": "场景", "content": "婚礼蛋糕/宝宝宴/庆典蛋糕大分量标配，10人份一盒搞定", "priority": 2},
            {"point_type": "性价比", "content": "6件套2.5元，含刀叉盘勺纸巾全套，超高性价比", "priority": 3},
        ]
    },
    {
        "name": "定制款刀叉盘套装",
        "category": "烘焙配件",
        "price": 3.5,
        "original_price": 8.0,
        "commission_rate": 15.0,
        "brand": "法采",
        "description": "定制LOGO/文字刀叉盘套装，品牌私房专属，可印店名/logo/祝福语",
        "selling_points": [
            {"point_type": "功效", "content": "印上你的店名和logo，每一份蛋糕都是品牌推广", "priority": 1},
            {"point_type": "场景", "content": "私房烘焙品牌专属，定制款让客户记住你", "priority": 2},
            {"point_type": "痛点", "content": "最低起订量友好，小私房也能有自己的定制刀叉", "priority": 3},
        ]
    },
]

# =========================================================
# 种子数据导入
# =========================================================

def seed_products(force=False):
    """导入法采全系列产品数据。force=True 时强制清空重新导入"""
    db = SessionLocal()
    try:
        from models import GeneratedScript, SellingPoint, Product
        # 检测已有数据，非强制模式直接跳过
        existing = db.query(Product).count()
        if existing > 0 and not force:
            print(f"  ℹ️  产品数据已存在（{existing} 条），跳过导入。如需重新导入请传入 force=True")
            return
        if force:
            # 强制模式才清空旧数据
            db.query(GeneratedScript).delete()
            db.query(SellingPoint).delete()
            db.query(Product).delete()
            db.commit()
            print("  已清空旧产品数据（强制模式）")

        # 批量导入
        total = len(FAICAI_PRODUCTS)
        for i, pdata in enumerate(FAICAI_PRODUCTS):
            sps = pdata.pop("selling_points", [])
            product = Product(**pdata)
            db.add(product)
            db.flush()

            for sp in sps:
                selling_point = SellingPoint(product_id=product.id, **sp)
                db.add(selling_point)

            if (i + 1) % 20 == 0 or i == total - 1:
                print(f"  导入进度: {i+1}/{total}")

        db.commit()
        print(f"  ✅ 已导入 {total} 个法采产品，涵盖5大系列")
        print(f"     - 调色系列: 14个")
        print(f"     - 装饰系列: 11个")
        print(f"     - 调味系列: 17个")
        print(f"     - 夹心系列: 8个")
        print(f"     - 刀叉配件系列: 5个")
        print(f"     共计: {total} 个")
    except Exception as e:
        db.rollback()
        print(f"  ❌ 导入失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    from database import init_db
    init_db()
    seed_products()
