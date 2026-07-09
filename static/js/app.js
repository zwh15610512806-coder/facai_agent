/**
 * 短视频脚本生成 Agent — 前端交互逻辑
 */

// ========== 品类→推荐视频类型映射 ==========
const CATEGORY_RECOMMENDATIONS = {
    "美妆护肤": ["需求类", "痛点类", "对比类", "达人分享类"],
    "3C数码": ["对比类", "认知类", "达人分享类", "成本低"],
    "食品饮料": ["场景类", "情绪类", "成本低"],
    "家居日用": ["机制类", "成本低", "需求类"],
    "服饰配饰": ["达人分享类", "场景类", "情绪类"],
    "运动户外": ["对比类", "场景类", "认知类"],
    // 法采烘焙品类
    "烘焙调色": ["对比类", "场景类", "机制类", "认知类"],
    "烘焙装饰": ["场景类", "达人分享类", "需求类"],
    "烘焙调味": ["需求类", "对比类", "认知类"],
    "烘焙夹心": ["制作方便", "成本低", "痛点类"],
    "烘焙配件": ["机制类", "成本低", "对比类"],
};

// ========== 主组件 ==========
function scriptGenerator() {
    return {
        // 步骤状态
        step: 1,

        // 产品数据
        products: [],
        categories: [],
        selectedProduct: null,
        loadingProducts: false,
        searchQuery: "",
        filterCategory: "",

        // 视频类型
        videoTypes: [
            { value: "机制类", label: "机制类", icon: "⚙️" },
            { value: "痛点类", label: "痛点类", icon: "⚠️" },
            { value: "需求类", label: "需求类", icon: "🔎" },
            { value: "认知类", label: "认知类", icon: "🧠" },
            { value: "达人分享类", label: "达人分享类", icon: "👥" },
            { value: "制作方便", label: "制作方便", icon: "🔧" },
            { value: "成本低", label: "成本低", icon: "💵" },
            { value: "对比类", label: "对比类", icon: "↔️" },
            { value: "情绪类", label: "情绪类", icon: "♡" },
            { value: "场景类", label: "场景类", icon: "📍" },
        ],
        selectedType: "",
        typeDescriptions: {
            "机制类": "机制钩子 → 规则拆解 → 产品承接 → 利益证明 → CTA。讲清为什么现在值得买",
            "痛点类": "痛点场景 → 情绪放大 → 产品解决 → 效果对比 → CTA。精准说中用户麻烦",
            "需求类": "用户需求 → 使用理由 → 卖点匹配 → 购买建议 → CTA。让用户意识到自己需要",
            "认知类": "认知反差 → 原理解释 → 产品验证 → 专业建议 → CTA。用知识建立信任",
            "达人分享类": "身份建立 → 真实体验 → 细节展示 → 自然推荐 → CTA。强调真实使用感",
            "制作方便": "省事钩子 → 操作演示 → 成品结果 → 下单理由 → CTA。降低上手门槛",
            "成本低": "成本钩子 → 成本对账 → 效果证明 → 性价比结论 → CTA。讲清实际省在哪里",
            "对比类": "对比问题 → 同屏对照 → 差异解释 → 结论推荐 → CTA。让差异一眼可见",
            "情绪类": "情绪引入 → 场景共鸣 → 产品释放 → 情绪收尾 → CTA。用情绪推动行动",
            "场景类": "场景建立 → 动作展示 → 成品呈现 → 场景转化 → CTA。让用户看见使用场景",
        },

        // 生成设置
        duration: "30-60s",
        tone: "活泼",
        extraRequirements: "",

        // 生成状态
        generating: false,
        scriptContent: "",
        scriptId: null,

        // 计算属性
        get recommendedTypes() {
            if (!this.selectedProduct) return [];
            return CATEGORY_RECOMMENDATIONS[this.selectedProduct.category] || ["机制类", "痛点类", "需求类"];
        },

        get formattedScript() {
            if (!this.scriptContent) return "";
            return this.scriptContent
                .replace(/【([^】]+)】/g, '<span class="tag">【$1】</span>')
                .replace(/\(\d+-\d+s\)/g, '<span class="time">$&</span>')
                .replace(/左下角/g, '<span class="cta-highlight">左下角</span>')
                .replace(/小黄车/g, '<span class="cta-highlight">小黄车</span>')
                .replace(/\n/g, '<br>');
        },

        // 初始化
        async init() {
            await this.loadProducts();
            await this.loadCategories();
        },

        // 加载产品
        async loadProducts() {
            this.loadingProducts = true;
            try {
                let url = "/api/products/";
                const params = new URLSearchParams();
                if (this.filterCategory) params.set("category", this.filterCategory);
                if (this.searchQuery) params.set("search", this.searchQuery);
                if (params.toString()) url += "?" + params.toString();

                const res = await fetch(url);
                this.products = await res.json();
            } catch (e) {
                console.error("加载产品失败:", e);
            } finally {
                this.loadingProducts = false;
            }
        },

        // 加载品类
        async loadCategories() {
            try {
                const res = await fetch("/api/products/categories");
                this.categories = await res.json();
            } catch (e) {
                console.error("加载品类失败:", e);
            }
        },

        // 搜索产品
        searchProducts() {
            this.loadProducts();
        },

        // 选择产品
        selectProduct(product) {
            this.selectedProduct = product;
            // 自动推荐视频类型
            const recs = CATEGORY_RECOMMENDATIONS[product.category] || [];
            if (recs.length > 0 && !this.selectedType) {
                // 不自动选择，只是高亮推荐
            }
        },

        // 选择视频类型
        selectType(type) {
            this.selectedType = this.selectedType === type ? "" : type;
        },

        getTypeDescription(type) {
            return this.typeDescriptions[type] || "";
        },

        getTypeLabel(type) {
            const vt = this.videoTypes.find(v => v.value === type);
            return vt ? vt.icon + " " + vt.label : type;
        },

        // 生成脚本
        async generateScript() {
            if (!this.selectedProduct || !this.selectedType) return;

            this.step = 3;
            this.generating = true;
            this.scriptContent = "";

            try {
                const res = await fetch("/api/scripts/generate", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        product_id: this.selectedProduct.id,
                        video_type: this.selectedType,
                        duration: this.duration,
                        tone: this.tone,
                        extra_requirements: this.extraRequirements || null,
                    }),
                });

                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(err.detail || "生成失败");
                }

                const data = await res.json();
                this.scriptContent = data.script_content;
                this.scriptId = data.id;
            } catch (e) {
                this.scriptContent = "❌ 生成失败：" + e.message + "\n\n请检查 AI 模型 API Key 和 Base URL 是否已配置（.env 文件或 AI 配置页）";
            } finally {
                this.generating = false;
            }
        },

        // 重新生成
        async regenerate() {
            await this.generateScript();
        },

        // 复制脚本
        async copyScript() {
            try {
                await navigator.clipboard.writeText(this.scriptContent);
                this.showToast("已成功复制到剪贴板", "success");
            } catch (e) {
                // fallback
                const textarea = document.createElement("textarea");
                textarea.value = this.scriptContent;
                document.body.appendChild(textarea);
                textarea.select();
                document.execCommand("copy");
                document.body.removeChild(textarea);
                this.showToast("已成功复制到剪贴板", "success");
            }
        },

        // Toast 通知
        showToast(message, type = "info") {
            const toast = document.createElement("div");
            toast.className = `toast toast-${type}`;
            toast.textContent = message;
            document.body.appendChild(toast);
            setTimeout(() => {
                toast.style.opacity = "0";
                toast.style.transition = "opacity .3s";
                setTimeout(() => toast.remove(), 300);
            }, 2500);
        },
    };
}

// ========== 产品管理页组件 ==========
function productManager() {
    return {
        products: [],
        categories: [],
        loading: false,
        showForm: false,
        editingProduct: null,
        searchQuery: "",
        filterCategory: "",

        // 表单数据
        form: {
            name: "", category: "", price: "", original_price: "",
            commission_rate: "", brand: "", description: "",
        },
        sellingPoints: [],

        async init() {
            await this.loadProducts();
            await this.loadCategories();
        },

        async loadProducts() {
            this.loading = true;
            try {
                let url = "/api/products/";
                const params = new URLSearchParams();
                if (this.filterCategory) params.set("category", this.filterCategory);
                if (this.searchQuery) params.set("search", this.searchQuery);
                if (params.toString()) url += "?" + params.toString();
                const res = await fetch(url);
                this.products = await res.json();
            } finally {
                this.loading = false;
            }
        },

        async loadCategories() {
            const res = await fetch("/api/products/categories");
            this.categories = await res.json();
        },

        openCreateForm() {
            this.editingProduct = null;
            this.form = { name: "", category: "", price: "", original_price: "", commission_rate: "", brand: "", description: "" };
            this.sellingPoints = [];
            this.showForm = true;
        },

        async openEditForm(productId) {
            const res = await fetch(`/api/products/${productId}`);
            const p = await res.json();
            this.editingProduct = p;
            this.form = {
                name: p.name, category: p.category, price: p.price,
                original_price: p.original_price || "", commission_rate: p.commission_rate || "",
                brand: p.brand || "", description: p.description || "",
            };
            this.sellingPoints = p.selling_points.map(sp => ({
                point_type: sp.point_type, content: sp.content, priority: sp.priority
            }));
            this.showForm = true;
        },

        addSellingPoint() {
            this.sellingPoints.push({ point_type: "功效", content: "", priority: this.sellingPoints.length + 1 });
        },

        removeSellingPoint(index) {
            this.sellingPoints.splice(index, 1);
        },

        async saveProduct() {
            const payload = {
                ...this.form,
                price: parseFloat(this.form.price) || 0,
                original_price: this.form.original_price ? parseFloat(this.form.original_price) : null,
                commission_rate: parseFloat(this.form.commission_rate) || 0,
                selling_points: this.sellingPoints.filter(sp => sp.content.trim()),
            };

            const url = this.editingProduct
                ? `/api/products/${this.editingProduct.id}`
                : "/api/products/";
            const method = this.editingProduct ? "PUT" : "POST";

            const res = await fetch(url, {
                method,
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });

            if (res.ok) {
                this.showForm = false;
                await this.loadProducts();
                this.showToast(this.editingProduct ? "产品已更新" : "产品已创建", "success");
            } else {
                const err = await res.json();
                this.showToast("保存失败：" + JSON.stringify(err.detail), "error");
            }
        },

        async deleteProduct(productId) {
            if (!confirm("确定删除该产品？此操作不可撤销。")) return;
            const res = await fetch(`/api/products/${productId}`, { method: "DELETE" });
            if (res.ok) {
                await this.loadProducts();
                this.showToast("产品已删除", "success");
            }
        },

        showToast(message, type) {
            const toast = document.createElement("div");
            toast.className = `toast toast-${type}`;
            toast.textContent = message;
            document.body.appendChild(toast);
            setTimeout(() => { toast.style.opacity = "0"; toast.style.transition = "opacity .3s"; setTimeout(() => toast.remove(), 300); }, 2500);
        },

        formatPrice(v) { return v ? "¥" + v : "-"; },
    };
}

// ========== 数据导入页组件 ==========
function dataImporter() {
    return {
        file: null,
        fileName: "",
        importing: false,
        result: null,
        dragOver: false,

        handleDrop(e) {
            this.dragOver = false;
            const files = e.dataTransfer.files;
            if (files.length > 0) this.setFile(files[0]);
        },

        handleFileInput(e) {
            const files = e.target.files;
            if (files.length > 0) this.setFile(files[0]);
        },

        setFile(f) {
            this.file = f;
            this.fileName = f.name;
            this.result = null;
        },

        async importFile() {
            if (!this.file) return;
            this.importing = true;
            this.result = null;

            const formData = new FormData();
            formData.append("file", this.file);

            const isExcel = this.fileName.endsWith(".xlsx");
            const endpoint = isExcel ? "/api/import/excel" : "/api/import/csv";

            try {
                const res = await fetch(endpoint, { method: "POST", body: formData });
                this.result = await res.json();
            } catch (e) {
                this.result = { errors: ["网络请求失败: " + e.message] };
            } finally {
                this.importing = false;
            }
        },

        get hasErrors() {
            return this.result && this.result.errors && this.result.errors.length > 0;
        },

        downloadTemplate() {
            window.open("/api/import/template", "_blank");
        },
    };
}

// ========== 模板库页组件 ==========
function templateLibrary() {
    return {
        templates: [],
        viralScripts: [],
        loading: false,
        filterType: "",
        selectedTemplate: null,

        async init() {
            await this.loadTemplates();
            await this.loadViralScripts();
        },

        async loadTemplates() {
            this.loading = true;
            let url = "/api/templates/";
            if (this.filterType) url += "?video_type=" + encodeURIComponent(this.filterType);
            const res = await fetch(url);
            this.templates = await res.json();
            this.loading = false;
        },

        async loadViralScripts() {
            const res = await fetch("/api/templates/viral/list");
            this.viralScripts = await res.json();
        },

        async viewTemplate(tpl) {
            this.selectedTemplate = tpl;
        },

        get videoTypes() {
            const types = new Set();
            this.templates.forEach(t => types.add(t.video_type));
            return [...types];
        },
    };
}

// ========== 生成历史页组件 ==========
function scriptHistory() {
    return {
        scripts: [],
        loading: false,
        filterProduct: "",

        async init() {
            await this.loadHistory();
        },

        async loadHistory() {
            this.loading = true;
            let url = "/api/scripts/history";
            if (this.filterProduct) url += "?product_id=" + this.filterProduct;
            const res = await fetch(url);
            this.scripts = await res.json();
            this.loading = false;
        },

        async copyScript(content) {
            try {
                await navigator.clipboard.writeText(content);
                this.showToast("已成功复制到剪贴板", "success");
            } catch {
                const ta = document.createElement("textarea");
                ta.value = content;
                document.body.appendChild(ta);
                ta.select();
                document.execCommand("copy");
                document.body.removeChild(ta);
                this.showToast("已成功复制到剪贴板", "success");
            }
        },

        async deleteScript(id) {
            if (!confirm("确定删除此记录？")) return;
            await fetch(`/api/scripts/history/${id}`, { method: "DELETE" });
            await this.loadHistory();
            this.showToast("记录已删除", "success");
        },

        showToast(message, type) {
            const toast = document.createElement("div");
            toast.className = `toast toast-${type}`;
            toast.textContent = message;
            document.body.appendChild(toast);
            setTimeout(() => { toast.style.opacity = "0"; toast.style.transition = "opacity .3s"; setTimeout(() => toast.remove(), 300); }, 2500);
        },

        formatDate(d) { return new Date(d).toLocaleString("zh-CN"); },

        preview(content) {
            return content ? content.substring(0, 150) + "..." : "";
        },
    };
}
