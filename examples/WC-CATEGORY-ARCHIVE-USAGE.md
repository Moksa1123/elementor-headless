# WooCommerce 商品分類 Archive 頁面模板

用 Elementor Pro 內建功能實現：
1. **母分類頁面** — 頂部可滑動的子分類選單
2. **子分類頁面** — 下方相關分類推薦區

**不需要自己寫程式碼。**

---

## 結構

### 容器 1：子分類導航（頂部）
```
wc-categories widget
├─ source: "by_parent"        ← 按母分類顯示
├─ parent: "0"                ← 當前母分類 ID（自動填充）
├─ columns: 6 (desktop)       ← 可滑動列表
└─ hide_empty: yes
```

### 容器 2：主要內容（中間）
```
├─ woocommerce-breadcrumb     ← 麵包屑導航
├─ theme-archive-title        ← 分類名稱
├─ woocommerce-archive-description  ← 分類描述
└─ woocommerce-products       ← 商品列表 (4 列網格)
```

### 容器 3：相關分類（下方）
```
wc-categories widget
├─ source: "current_subcategories"  ← 同級子分類
├─ columns: 4
└─ hide_empty: yes
```

---

## 使用步驟

### 1. 建立 Theme Builder 模板

```bash
# WordPress 後台
Elementor > Templates > Create New
├─ Name: "WooCommerce Category Archive"
├─ Type: "Archive"
└─ Category: "Product Category"
```

### 2. 上傳頁面 JSON

```bash
# 本地
wp eval-file tools/import-template.php examples/wc-category-archive-template.json

# 將生成的 template ID 套用到所有商品分類頁面
```

### 3. 設定條件

在 Theme Builder 中：
```
Display Conditions
├─ Post Type: Product Category
└─ All Categories
```

---

## 自訂選項

### 修改子分類列數

編輯 JSON 中的第一個容器：
```json
"columns": "6",           // Desktop: 6 個
"columns_tablet": "4",    // Tablet: 4 個
"columns_mobile": "2"     // Mobile: 2 個
```

### 修改相關分類標題

編輯第三個容器中的 heading：
```json
"title": "也許你也需要……"
```

### 修改商品列數

編輯中間容器的 woocommerce-products：
```json
"columns": "4",           // Desktop
"columns_tablet": "2",    // Tablet
"columns_mobile": "1"     // Mobile
```

---

## 注意事項

1. **`parent: "0"`** 會自動判讀當前母分類
   - Elementor Pro 的動態內容會填入實際的 term ID
   
2. **`source: "current_subcategories"`** 只在子分類頁面有效
   - 母分類頁面上不會顯示（因為沒有「當前子分類」）

3. 所有控制項都是 **Elementor Pro 專用**
   - 需要 WooCommerce 外掛
   - 需要 Elementor Pro 4.2.0+

---

## 驗證

```bash
# 本地驗證
python tools/validate-page.py examples/wc-category-archive-template.json \
  --target pro --have woocommerce

# 結果應該是 0 errors
```

---

## 實際效果

- ✅ 母分類頁面：頂部滑動子分類選單（紅色區域）
- ✅ 子分類頁面：下方相關分類推薦卡片（綠色區域）
- ✅ 完全響應式（mobile/tablet/desktop）
- ✅ 無需自訂程式碼
