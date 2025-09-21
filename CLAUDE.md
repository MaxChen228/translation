# Translation Backend

## 標籤體系規範

本系統使用標準化的63個標籤，分為5大類：

### 語法結構 (18個)
`subjunctive` `conditional` `cleft` `inversion` `emphasis` `comparative` `superlative` `passive` `modal` `infinitive` `gerund` `participle` `relative-clause` `noun-clause` `adverb-clause` `as-clause` `complex-sentence` `grammar`

### 特定結構 (15個)
`as-adjective-as` `as-soon-as` `as-long-as` `as-far-as` `the-more-the-more` `would-rather` `had-better` `used-to` `be-used-to` `too-to` `so-that` `such-that` `not-only-but-also` `either-or` `neither-nor`

### 語法功能 (19個)
`advice` `warning` `request` `permission` `prohibition` `suggestion` `offer` `invitation` `complaint` `apology` `opinion` `preference` `regret` `possibility` `necessity` `ability` `purpose` `result` `cause`

### 語意主題 (18個)
`family` `education` `career` `health` `money` `relationship` `travel` `food` `sports` `entertainment` `technology` `environment` `culture` `business` `academic` `personal` `social` `daily-life`

### 時態語態 (8個)
`present-simple` `present-continuous` `present-perfect` `past-simple` `past-continuous` `past-perfect` `future-simple` `future-perfect`

## 強制規範
- **僅可使用上述63個標籤**
- 每題目2-4個標籤
- 小寫連字號格式
- 禁止創建新標籤

## 驗證工具
```bash
python TAG_VALIDATION_SCRIPT.py data/books
```

## 標籤選擇原則
1. 語法重點：選語法結構類
2. 交際功能：選功能類
3. 內容主題：選1-2個主題類
4. 避免重複意義的標籤

範例：
```json
{
  "zh": "如果我是你，我就會聽他的勸告。",
  "tags": ["conditional", "subjunctive", "advice", "personal"]
}
```