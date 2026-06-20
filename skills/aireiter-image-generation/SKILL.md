---
name: aireiter-image-generation
description: 浣跨敤 AIReiter 绗笁鏂瑰浘鐗囩敓鎴愭帴鍙ｆ彁浜ゅ紓姝ユ枃鐢熷浘/鍥剧敓鍥句换鍔★紝鏀寔鍦?Codex 涓寚瀹氭ā鍨嬶紙濡?GPT-Image-2銆丯ano Banana V2 / nanobanana V2锛夈€佹湰鍦板浘鐗囪矾寰勮嚜鍔ㄨ浆 base64 data URL锛屽苟杞鏌ヨ缁撴灉銆傞€傜敤浜庣敤鎴疯鈥滀娇鐢?aireiter 鐢熸垚鍥剧墖鈥濃€滀娇鐢?aireiter 鐨?nanobanana V2 妯″瀷鐢熸垚鍥剧墖鈥濈瓑鍦烘櫙銆?license: MIT
metadata:
  hermes:
    tags: [image-generation, aireiter, async-api, base64, cross-agent]
---

# AIReiter 鍥剧墖鐢熸垚

## 鍓嶇疆鏉′欢

- `python3` 鎴栧綋鍓?agent 鑷甫鐨?Python 杩愯鏃?- 涓嶄娇鐢?helper 鑴氭湰銆佺洿鎺ヨ皟鐢?API 鏃堕渶瑕?`curl`

## Codex 妯″瀷璺敱

褰撶敤鎴峰湪 Codex 涓姹備娇鐢?AIReiter 鐢熷浘鏃讹紝蹇呴』浣跨敤鏈?skill銆傝嫢鐢ㄦ埛鎸囧畾妯″瀷锛屾寜涓嬮潰瑙勫垯浼犵粰 `scripts/aireiter_image_helper.py submit --model`锛涜嫢鏈寚瀹氭ā鍨嬶紝榛樿浣跨敤 `gpt_image_2`銆傞粯璁ゅ垎杈ㄧ巼淇濇寔 `2K`銆?
甯哥敤妯″瀷鍒悕锛?- `gpt_image_2`锛氶粯璁ゆā鍨嬶紱涔熸帴鍙?`gpt-image-2`銆乣gpt image 2`銆?- `nano_banana_v2`锛歂ano Banana V2 榛樿閫氶亾锛涗篃鎺ュ彈 `nanobanana V2`銆乣nano banana v2`銆乣nano-banana-v2`銆?- `nano_banana_v2_base` / `nano_banana_v2_plus` / `nano_banana_v2_max`锛歂ano Banana V2 鐨勫熀纭€鐗堛€佸寮虹増銆佹棗鑸扮増锛涢€氶亾鍙奖鍝嶆湇鍔＄ǔ瀹氭€э紝涓嶅奖鍝嶈緭鍑鸿川閲忋€?
绀轰緥锛氱敤鎴疯鈥滀娇鐢?aireiter 鐨?nanobanana V2 妯″瀷锛岀敓鎴愪竴寮犲皬鐚殑鍥剧墖鈥濇椂锛岃皟鐢細

```bash
python3 scripts/aireiter_image_helper.py submit \
  --model nano_banana_v2 \
  --prompt '涓€寮犲皬鐚殑鍥剧墖' \
  --resolution 2K
```

Nano Banana V2 鍙傛暟绾︽潫锛歚params.prompt` 蹇呭～锛沗params.image_url` 鍙€変笖鏈€澶?8 寮狅紝鏀寔鍏紑 URL 鎴栧畬鏁?Data URI锛沗params.aspect_ratio` 鏀寔 `auto`銆乣1:1`銆乣3:2`銆乣2:3`銆乣4:3`銆乣3:4`銆乣5:4`銆乣4:5`銆乣16:9`銆乣9:16`銆乣21:9`锛沗params.resolution` 鏀寔 `1K`銆乣2K`銆乣4K`锛屾湰 skill 榛樿浼?`2K`銆?
閫氳繃 AIReiter 鐨勫紓姝ヤ换鍔℃帴鍙ｇ敓鎴愬浘鐗囷紝榛樿妯″瀷涓?`gpt_image_2`锛屼篃鍙寜鐢ㄦ埛瑕佹眰鎸囧畾 Nano Banana V2 绛夊彈鏀寔妯″瀷銆傛敮鎸侊細
- 鏂囩敓鍥?- 鍥剧敓鍥撅紙鍙傝€冨浘 URL锛?- 鍥剧敓鍥撅紙鏈湴鍥剧墖璺緞鑷姩杞?`data:*;base64,...`锛?- 鎻愪氦浠诲姟鍚庤疆璇㈡煡璇㈢粨鏋?- 鍦ㄤ笉鍚?agent 涓鐢ㄥ悓涓€濂楀懡浠ゅ拰鑴氭湰

## 閫傜敤鍦烘櫙

褰撶敤鎴疯姹傦細
- 閫氳繃绗笁鏂规帴鍙ｇ敓鎴愬浘鐗?- 璋冪敤 AIReiter 鐨?GPT-Image-2銆丯ano Banana V2 绛夊浘鐗囩敓鎴愭帴鍙?- 涓婁紶鏈湴鍥剧墖浣滀负鍙傝€冨浘
- 鍦?Hermes / Codex / Codex / OpenCode 涓鐢ㄧ浉鍚屽伐浣滄祦

## 鎺ュ彛鎽樿

### 1) 鎻愪氦浠诲姟
- Endpoint: `POST https://aireiter.com/api/openapi/submit`
- Header:
  - `Authorization: Bearer <API_KEY>`
  - `Content-Type: application/json`
- 妯″瀷鍚嶏細榛樿 `gpt_image_2`锛屽彲閫氳繃 `--model` 鎸囧畾 `nano_banana_v2` 绛夋ā鍨?- 璇锋眰浣撻《灞傚瓧娈碉細
  - `model`: 榛樿 `gpt_image_2`锛涚敤鎴锋寚瀹?Nano Banana V2 鏃朵紶 `nano_banana_v2` 鎴栧搴旈€氶亾妯″瀷
  - `params`: 妯″瀷鍙傛暟瀵硅薄
  - `out_task_id`: 璋冪敤鏂硅嚜瀹氫箟浠诲姟 ID锛屽繀濉?
### 2) 鏌ヨ浠诲姟鐘舵€?- Endpoint: `POST https://aireiter.com/api/openapi/query`
- Header 鍚屼笂
- 璇锋眰浣擄細`{"out_task_id":"..."}`

### 3) 浠诲姟鐘舵€?- `pending`: 鎺掗槦涓?- `processing`: 澶勭悊涓?- `completed`: 瀹屾垚锛屽彲浠?`data.output[].url` 鍙栫粨鏋?- `failed`: 澶辫触锛屽彲妫€鏌?`data.error`

## 鍏抽敭绾︽潫

- 璇ユ帴鍙ｆ槸寮傛妯″紡锛屾彁浜ゅ悗涓嶄細鐩存帴杩斿洖鍥剧墖 URL銆?- `out_task_id` 蹇呭～锛屽缓璁甫鏃堕棿鎴抽伩鍏嶅啿绐併€?- 鍙傝€冨浘鏁伴噺鎸夋ā鍨嬬害鏉熸墽琛岋細`gpt_image_2` 閫氬父鏈€澶?9 寮狅紱Nano Banana V2 鏈€澶?8 寮狅紱鏀寔 URL 涓?base64 娣峰～銆?- 鏈湴鍥剧墖蹇呴』鍏堣浆涓?base64 data URL 鍐嶆斁鍏ヨ姹傚弬鏁般€?- 澶氬紶鍙傝€冨浘蹇呴』浠ユ暟缁勫舰寮忎紶鍏?`params.image_url`锛屼笉瑕佹妸澶氫釜 data URI 鐢ㄨ嫳鏂囬€楀彿鎷兼帴銆?- 椋炰功鎴栧叾浠栭檮浠跺浘鐗囧昂瀵歌繃澶ф椂锛屽簲鍏堜笅杞藉師鍥惧埌鏈湴锛屽啀鐢熸垚鍘嬬缉鍓湰鐢ㄤ簬鎻愪氦锛涙帹鑽愭渶闀胯竟 `1280px`銆丣PEG銆乹uality `84`銆?- 鎻愪氦鍐呭浼氱粡杩囧钩鍙板畨鍏ㄥ鏍革紝杩濊鍐呭鍙兘鐩存帴澶辫触銆?
## 鎺ㄨ崘鍙傛暟绾﹀畾

甯哥敤 `params` 瀛楁锛?- `prompt`: 蹇呭～锛屽浘鐗囩敓鎴愭彁绀鸿瘝
- `aspect_ratio`: 鍙€夛紝榛樿 `3:4`锛屼緥濡?`1:1`銆乣3:4`銆乣16:9`銆乣9:16`
- `resolution`: 鍙€夛紝榛樿 `2K`锛圓IReiter API 瑕佹眰澶у啓 K锛?- `image_url`: 鍙€夛紱褰撳仛鍥剧敓鍥捐緭鍏ユ椂鍙紶锛?  - 鍗曚釜 URL
  - 澶氫釜 URL / data URL 缁勬垚鐨勬暟缁?  - 鍗曚釜鎴栧涓?base64 data URL
  - URL + base64 娣峰悎鏁扮粍

濡傛灉鏂囨。鍚庣画鏂板瀛楁锛屼互鏈€鏂?API 鏂囨。涓哄噯锛涙湰鎶€鑳藉厛瑕嗙洊鏂囨。鏄庣‘缁欏嚭鐨勯€氱敤绋冲畾瀛楁銆?
## API Key 浼犻€掓柟寮?
闄勫甫鑴氭湰鐜板湪鍚屾椂鏀寔涓ょ鏂瑰紡锛?
1. 鏄惧紡浼犲弬锛?
```bash
python3 scripts/aireiter_image_helper.py submit --api-key '浣犵殑_api_key' --prompt '...'
```

2. 鍏堣缃湰鍦扮幆澧冨彉閲忥紝涔嬪悗鎻愪氦鏃跺彲鐪佺暐 `--api-key`锛?
```bash
export AIREITER_API_KEY='浣犵殑_api_key'
python3 scripts/aireiter_image_helper.py submit --prompt '...'
```

3. 浣跨敤鎶€鑳藉唴閰嶇疆鏂囦欢锛歚references/config.json`锛屽瓧娈典负 `api_key`銆傝剼鏈細鎸?`--api-key` 鈫?`AIREITER_API_KEY` 鈫?`references/config.json` 鐨勯『搴忚鍙栥€?
褰撳墠鏈湴鎶€鑳藉凡鍐欏叆鐢ㄦ埛鎺堟潈鎻愪緵鐨?AIReiter API key锛屽彲鐩存帴鐪佺暐 `--api-key` 璋冪敤 `submit` / `query` / `wait`銆?
## 鏈€鐭彲鐢細绾枃鐢熷浘

```bash
API_KEY='浣犵殑_api_key'
TASK_ID="aireiter-$(date +%Y%m%d-%H%M%S)"

curl --request POST \
  --url https://aireiter.com/api/openapi/submit \
  --header "Authorization: Bearer ${API_KEY}" \
  --header 'Content-Type: application/json' \
  --data "{
    \"model\": \"gpt_image_2\",
    \"params\": {
      \"prompt\": \"涓€鍙摱鑹叉満姊扮尗韫插湪闇撹櫣闆ㄥ鐨勪究鍒╁簵闂ㄥ彛锛岀數褰辨劅锛岄珮缁嗚妭\",
      \"aspect_ratio\": \"3:4\",
      \"resolution\": \"2K\"
    },
    \"out_task_id\": \"${TASK_ID}\"
  }"
```

鏌ヨ缁撴灉锛?
```bash
curl --request POST \
  --url https://aireiter.com/api/openapi/query \
  --header "Authorization: Bearer ${API_KEY}" \
  --header 'Content-Type: application/json' \
  --data "{\"out_task_id\":\"${TASK_ID}\"}"
```

## 鏈湴鍥剧墖杞?base64 data URL

浼樺厛浣跨敤鏈?skill 闄勫甫鑴氭湰锛歚scripts/aireiter_image_helper.py`

鍗曞浘杞爜锛?
```bash
python3 scripts/aireiter_image_helper.py encode /absolute/path/to/input.png
```

杈撳嚭浼氭槸锛?
```text
data:image/png;base64,iVBORw0K...
```

## 鎺ㄨ崘宸ヤ綔娴侊細鑴氭湰鎻愪氦 + 杞

鏈?skill 鑷甫鑴氭湰鏀寔鎻愪氦銆佹煡璇€佺瓑寰呭畬鎴愩€?
### 1) 绾枃鐢熷浘

```bash
export AIREITER_API_KEY='浣犵殑_api_key'
python3 scripts/aireiter_image_helper.py submit \
  --prompt '鍖楁鏋佺畝椋庡鍘咃紝娓呮櫒闃冲厜锛屾潅蹇楀皝闈㈡憚褰? \
  --aspect-ratio '16:9' \
  --resolution '2K'
```

### 2) 鍥剧敓鍥撅細杩滅▼鍙傝€冨浘

```bash
python3 scripts/aireiter_image_helper.py submit \
  --api-key '浣犵殑_api_key' \
  --prompt '鎶婅繖寮犱骇鍝佸浘鏀规垚鑻规灉鍙戝竷浼氭捣鎶ラ鏍硷紝淇濈暀涓讳綋' \
  --aspect-ratio '3:4' \
  --resolution '2K' \
  --image 'https://example.com/reference-1.jpg' \
  --image 'https://example.com/reference-2.png'
```

### 3) 鍥剧敓鍥撅細鏈湴鍙傝€冨浘

```bash
python3 scripts/aireiter_image_helper.py submit \
  --api-key '浣犵殑_api_key' \
  --prompt '淇濈暀鏋勫浘锛屾妸杩欏紶鑽夊浘娓叉煋鎴愰珮绔?3D 浜у搧鏁堟灉鍥? \
  --aspect-ratio '3:4' \
  --resolution '2K' \
  --image '/absolute/path/to/sketch.png'
```

### 4) 绛夊緟浠诲姟瀹屾垚

```bash
python3 scripts/aireiter_image_helper.py wait \
  --api-key '浣犵殑_api_key' \
  --task-id 'aireiter-20260101-120000'
```

榛樿姣?5 绉掕疆璇竴娆★紝鐩村埌锛?- 鎴愬姛锛氭墦鍗板畬鏁?JSON锛岀粨鏋滃浘鐗囧湪 `data.output[].url`
- 澶辫触锛氭墦鍗伴敊璇苟浠ラ潪 0 鐘舵€侀€€鍑?
## 璺?agent 澶嶇敤鏂瑰紡

### Hermes
鐩存帴鍔犺浇鏈妧鑳藉苟鎵ц鑴氭湰鎴?curl 鍛戒护銆?
### Codex / Codex / OpenCode
杩欎簺 agent 鍗充娇娌℃湁 Hermes 鐨?skill 杩愯鏃讹紝涔熷彲浠ョ洿鎺ュ鐢細
- 鐩稿悓鐨?API endpoint
- 鐩稿悓鐨?`--api-key` 鍙傛暟椋庢牸
- 鐩稿悓鐨?`out_task_id` + 鏌ヨ杞妯″紡
- 鐩稿悓鐨勬湰鍦版枃浠惰嚜鍔ㄨ浆 data URL 閫昏緫

杩欎釜 skill 鐨勬牳蹇冧环鍊兼槸鎶婃帴鍙ｇ害瀹氥€佸懡浠ゆā鏉裤€乥ase64 杞崲鏂瑰紡鍜岃疆璇㈡祦绋嬪浐鍖栦笅鏉ワ紝渚夸簬涓嶅悓 agent 鐩存帴鐓ф惉銆?
## 瀹炴垬瑕佹眰

鎵ц鍥剧墖鐢熸垚浠诲姟鏃讹紝鎸夎繖涓『搴忥細

1. 鍑嗗 API key銆?2. 鑻ユ湁鏈湴鍥剧墖璺緞锛屽厛杞负 data URL锛屾垨鐩存帴浣跨敤闄勫甫鑴氭湰鎻愪氦銆?3. 鐢熸垚鍞竴 `out_task_id`銆?4. 璋冪敤 `submit`銆?5. 璁板綍 `out_task_id`銆?6. 璋冪敤 `query` 鎴?`wait` 鐩村埌浠诲姟缁撴潫銆?7. 杩斿洖缁撴灉 URL锛屽繀瑕佹椂闄勪笂浠诲姟鐘舵€佸拰娑堣€楃Н鍒嗐€?
## 澶辫触鍏滃簳瑙勫垯

- 濡傛灉 AIReiter 浠诲姟鏈€缁堣繑鍥?`failed`銆佽疆璇㈣秴鏃躲€佹彁浜?鏌ヨ鍛戒护闈?0 閫€鍑猴紝鎴栨帴鍙ｈ繑鍥炴棤鍙敤 `data.output[].url`锛岃涓?AIReiter 鐢熸垚澶辫触銆?- 鎻愪氦鍝嶅簲涔熷繀椤讳弗鏍煎垽瀹氾細`ok: true` 涓嶇瓑浜庝换鍔″凡杩涘叆闃熷垪銆傚彧瑕佸搷搴旈噷鍑虹幇 `statusCode >= 400`銆乣message`/`error` 鍖呭惈 `not enough credits`銆乣forbidden`銆乣unauthorized`銆乣failed`銆乣error`锛屾垨娌℃湁鍙瘉鏄庝换鍔″凡琚帴鍙楃殑鏁版嵁锛岄兘瑙嗕负 AIReiter 鎻愪氦澶辫触銆傚吀鍨嬪け璐ョず渚嬶細`{"ok": true, "statusCode": 433, "message": "not enough credits", "data": null}`銆?- AIReiter 鐢熸垚澶辫触鍚庯紝涓嶈绔嬪嵆涓锛涜嚜鍔ㄨ繘鍏ユ湰鍦?Codex `.system/imagegen` skill 鐨勯粯璁ゅ伐浣滄祦閲嶈瘯涓€娆＄敓鎴愶紝灏介噺澶嶇敤鍘熷 prompt銆佸楂樻瘮銆佸弬鑰冨浘鍜屼富瑕佺害鏉熴€?- 杩涘叆 `imagegen` 鍏滃簳鏃讹紝璇诲彇骞堕伒寰?`$CODEX_HOME/skills/.system/imagegen/SKILL.md`锛堟湭璁剧疆 `CODEX_HOME` 鏃朵负 `~/.codex/skills/.system/imagegen/SKILL.md`锛夌殑瑙勫垯锛沇indows 榛樿閫氬父瀵瑰簲 `%USERPROFILE%\.codex\skills\.system\imagegen\SKILL.md`銆?- `imagegen` 鏄?Codex 鐨勬湰鍦?skill 宸ヤ綔娴侊紱涓嶈鎶?Hermes MCP 鏆撮湶鐨?`mcp__hermes_tools.image_generate` / `image_generate` 褰撲綔璇ュ厹搴曪紝闄ら潪鐢ㄦ埛鏄庣‘瑕佹眰浣跨敤 Hermes銆?- 濡傛灉褰撳墠 Codex 浼氳瘽娌℃湁鍙皟鐢ㄧ殑鍘熺敓 imagegen 鐢熷浘鑳藉姏锛屾垨 `imagegen` 涔熷け璐ワ紝绔嬪嵆涓褰撳墠鐢熷浘浠诲姟锛屼笉鍐嶇户缁皾璇曞叾浠栫敓鎴愰€氶亾锛涜繑鍥?AIReiter 閿欒銆乣imagegen` 涓嶅彲鐢?澶辫触淇℃伅浠ュ強宸叉墽琛岀殑鍏滃簳姝ラ銆?
## Codex imagegen 鍏滃簳缂栨帓

`imagegen` 鏄?Codex 鏈湴 `.system` skill锛宍image_gen` 鏄 skill 鏂囨。涓弿杩扮殑鐢熷浘鑳藉姏锛屼笉鏄?Python 鑴氭湰鍐呭彲鐩存帴璋冪敤鐨勫嚱鏁般€傚洜姝わ紝AIReiter helper 鑴氭湰鍙兘璐熻矗鎶婂け璐ヨ瘑鍒负闈?0 閫€鍑猴紱鐪熸鐨?imagegen 鍏滃簳蹇呴』鐢?Codex 缂栨帓灞傛寜 `imagegen` skill 鎵ц銆備笉瑕佹妸 Hermes MCP 鐨?`image_generate` 瑙嗕负鍚屼竴涓厹搴曢€氶亾銆?
褰?AIReiter 澶辫触鏃讹紝鎸変互涓嬫楠ゅ鐞嗭細

1. 淇濈暀鍘熷 `out_task_id`锛屼负鍏滃簳缁撴灉浣跨敤鍚屽悕鎴栬拷鍔?`fallback-imagegen` 鐨勬湰鍦版枃浠跺悕锛岄伩鍏嶄涪澶辫拷韪叧绯汇€?2. 璇诲彇澶辫触浠诲姟鐨勫師濮?prompt銆乤spect ratio銆乺eference images銆佷骇鍝佺害鏉熴€佸満鏅害鏉熷拰绂佹椤癸紱涓嶈閲嶆柊鍙戞槑 prompt銆?3. 濡傛灉鍙傝€冨浘鍦ㄦ湰鍦拌矾寰勪腑锛屽厛鐢?Codex `view_image` 鍔犺浇鍏抽敭浜у搧鍙傝€冨浘锛岃鍐呯疆 `image_gen` 鑳界湅瑙佸弬鑰冨浘锛涙壒閲忎换鍔℃瘡涓骇鍝佽嚦灏戝姞杞芥闈㈠浘鍜屽叧閿粏鑺傚浘锛屾潗璐ㄦ晱鎰熶骇鍝佽繕瑕佸姞杞戒晶瑙?鏉愯川缁嗚妭銆?4. 姣忔潯澶辫触浠诲姟璋冪敤涓€娆?`imagegen` skill 鐨勯粯璁ゅ唴缃?`image_gen`锛宲rompt 涓槑纭啓鍏ワ細
   - 澶嶇敤鍙傝€冨浘涓殑鐪熷疄浜у搧浣滀负鍞竴鐝犲疂涓讳綋锛?   - 淇濈暀鏉愯川銆侀鑹层€佺粨鏋勬瘮渚嬨€佺汗鐞嗐€侀厤浠朵綅缃紱
   - 鎵ц鍘熷 scene / lighting / style锛?   - 绂佹浜у搧鍙樺舰銆佸彉鑹层€侀噸澶嶅晢鍝併€佹枃瀛椼€佹按鍗般€乴ogo銆?5. `imagegen` 鐢熸垚鍚庯紝鎸?`imagegen` skill 鐨勪繚瀛樼瓥鐣ワ紝鎶婇粯璁ょ敓鎴愮洰褰曚腑鐨勫浘鐗囧鍒跺埌褰撳墠椤圭洰杈撳嚭鐩綍锛屼緥濡?`outputs/<run-id>/fallback-imagegen/<out_task_id>.png`锛涗笉瑕佸垹闄ら粯璁ょ敓鎴愮洰褰曢噷鐨勫師鍥俱€?6. 濡傛灉浠诲姟鏉ヨ嚜椋炰功 Base锛屼笂浼犲厹搴曞浘鐗囧埌缁撴灉琛ㄧ殑鍥剧墖/闄勪欢瀛楁锛岃褰曢敊璇俊鎭负鈥淎IReiter 澶辫触锛涘凡閫氳繃 imagegen fallback 琛ョ敓鎴愨€濓紝骞舵妸缁撴灉鐘舵€佹敼涓?`completed`銆傚鏋滀笂浼犻渶瑕佺敤鎴疯韩浠藉拰 `docs:document.media:upload` scope锛屽厛瀹屾垚椋炰功鎺堟潈鍐嶇户缁€?7. 鍏滃簳瀹屾垚鍚庨噸鏂拌鍙栫粨鏋滆〃楠岃瘉锛氬け璐ヤ换鍔℃暟閲忋€乣completed` 鏁伴噺銆佸浘鐗囬檮浠舵暟閲忓繀椤讳竴鑷达紱鍏宠仈浜у搧鍐嶄粠 `闇€閲嶈窇` 鏀瑰洖 `寰匭C`銆?
鎵归噺鍏滃簳鏃剁姝㈠彧鍦ㄦ湰鍦扮敓鎴愬浘鐗囧悗鍙ｅご瀹ｅ竷瀹屾垚锛涘繀椤诲畬鎴愭湰鍦版枃浠躲€佺粨鏋滆〃闄勪欢銆佺姸鎬佸瓧娈典笁椤瑰洖鍐欏拰楠岃瘉銆?
## 鏁呴殰鎺掓煡

- `401`锛欰PI key 鏃犳晥鎴栨湭浼犮€?- `400`锛氳姹?JSON 缁撴瀯閿欒锛屼紭鍏堟鏌?`model`銆乣params`銆乣out_task_id`銆?- 涓€鐩?`pending`锛氱户缁疆璇紝寮傛浠诲姟鍙兘鍦ㄦ帓闃熴€?- `failed`锛氭煡鐪嬭繑鍥?JSON 涓殑 `error` 瀛楁銆?- `433` / `not enough credits`锛氱Н鍒嗕笉瓒筹紝瑙嗕负鎻愪氦澶辫触锛涗笉瑕佹爣璁颁负 `submitted`锛屽簲绔嬪嵆杩涘叆 Codex `imagegen` 鍏滃簳缂栨帓銆?- 鏈湴鍥剧墖鏃犳硶鎻愪氦锛氱‘璁や娇鐢ㄧ粷瀵硅矾寰勶紝涓旀枃浠?MIME 绫诲瀷鍙瘑鍒€?- 澶氬紶鍥撅細閲嶅浼?`--image` 鍙傛暟锛岃剼鏈細鑷姩杞崲鎴?`params.image_url` 鏁扮粍銆?
## 杩斿洖缁撴灉鏃剁殑鏍囧噯鍋氭硶

鎴愬姛鏃朵紭鍏堣繑鍥烇細
- `out_task_id`
- 鏈€缁?`status`
- `credits_used`锛堝鏋滄煡璇㈢粨鏋滈噷鏈夛級
- `output` 涓叏閮ㄥ浘鐗?URL

澶辫触鏃惰繑鍥烇細
- `out_task_id`
- `status`
- `error` 鍘熸枃

## 闄勫甫鑴氭湰

- `scripts/aireiter_image_helper.py`
  - `encode`: 鏈湴鍥剧墖杞?data URL
  - `submit`: 鎻愪氦浠诲姟
  - `query`: 鏌ヨ浠诲姟鐘舵€?  - `wait`: 杞鐩村埌瀹屾垚鎴栧け璐?
## 瀹炴祴缁撹

杩欏娴佺▼宸茶鐪熷疄璋冪敤楠岃瘉锛?- 鏂囩敓鍥炬彁浜?+ 杞瀹屾垚锛氭垚鍔?- 浣跨敤鏈湴鍥剧墖璺緞鍋氬浘鐢熷浘锛氭垚鍔燂紝鑴氭湰浼氳嚜鍔ㄨ浆鎴?data URL 鍚庢彁浜?- `credits_used` 浼氬湪浠诲姟瀹屾垚鍚庣殑鏌ヨ缁撴灉閲岃繑鍥?- `task_id` 鍙兘鍦ㄥ垵娆℃彁浜よ繑鍥炰腑涓虹┖锛屼絾 `out_task_id` 鍙ǔ瀹氱敤浜庡悗缁煡璇?
## 缁忛獙澶囨敞

- 鏈湴鎶€鑳藉彲浠?`references/config.json` 璇诲彇榛樿 API key锛涜法 agent 杩佺Щ skill 鏃讹紝鑻ヤ笉鎯冲悓姝ュ瘑閽ユ枃浠讹紝涔熷彲浠ユ敼鐢ㄦ樉寮?`--api-key` 鎴栫幆澧冨彉閲?`AIREITER_API_KEY`銆?- 鑻ュ彧鏄兂澶嶇敤鏈湴鍥剧墖鍥剧敓鍥捐兘鍔涳紝鐩存帴浼犳枃浠惰矾寰勭粰 `--image` 鍗冲彲锛屾棤闇€鎵嬪姩鍏堟墽琛?`encode`銆?- 鏌愪簺瑙嗚鍒嗘瀽宸ュ叿閾惧彲鑳芥棤娉曠ǔ瀹氳鍙栨湰鍦板浘鍍忚繘琛屽垎鏋愶紝浣嗕笉褰卞搷鎶婃湰鍦板浘鐗囦綔涓哄浘鐢熷浘杈撳叆鎻愪氦缁?AIReiter銆?
## Web 宸ヤ綔鍙版帴鍏ョ粡楠?
褰撹鎶?AIReiter 鐨?prompt 鐢熸垚鑳藉姏鎺ュ叆涓€涓凡鏈?FastAPI Web 搴旂敤鏃讹紝浼樺厛鎸夆€滄ā鏉?+ 鍓嶇鑴氭湰 + 鏍峰紡 + 闆嗘垚娴嬭瘯鈥濆洓浠跺涓€璧锋敼锛屼笉瑕佸彧琛ヤ竴涓?API 鎸夐挳銆?
鎺ㄨ崘鍋氭硶锛?
1. 妯℃澘灞?- 鍦?`index.html` 涓妸 prompt builder 浣滀负鐙珛宸ヤ綔鍖猴紝鑷冲皯鏆撮湶绋冲畾鐨?DOM id锛?  - `builder-form`
  - `prompt-results`
  - `apply-prompt-btn`
- 璁?builder 涓庡師濮嬬敓鎴愯〃鍗曞苟瀛橈紝閬垮厤鎶婄敓鎴愯〃鍗曡亴璐ｅ拰 prompt 鐢熸垚鑱岃矗娣峰湪涓€涓?form 閲屻€?- 鑻ユ湁鈥滃甫鍏ヤ富鎻愮ず璇嶁€濇寜閽紝鐩爣 textarea 涔熻鏈夌ǔ瀹?id锛屼緥濡?`prompt`銆?
2. 鍓嶇鑴氭湰灞?- 鍗曠嫭鐩戝惉 `builder-form` 鐨?`submit`锛岃皟鐢?`/api/prompt-builder`銆?- 灏嗚繑鍥炲€兼媶鎴愪笁涓睍绀哄潡鏇存竻鏅帮細`prompt`銆乣fidelity_prompt`銆乣poster_prompt`銆?- 淇濆瓨鏈€杩戜竴娆¤繑鍥炲寘锛屾敮鎸侊細
  - 涓€閿甫鍏ヤ富鎻愮ず璇嶅埌姝ｅ紡鐢熸垚琛ㄥ崟
  - 鍗曠嫭澶嶅埗鏌愪釜鐗堟湰 prompt
- 淇濈暀鍘熸潵鐨勪换鍔℃彁浜や笌杞閫昏緫锛屼笉瑕佷负浜?builder 鏀瑰潖 `/api/generate` 鐨勬彁浜ゆ祦绋嬨€?
3. 鏍峰紡灞?- 濡傛灉妯℃澘閲屾柊澧炰簡 `builder-panel`銆乣prompt-results`銆乣prompt-card`銆乣toggle-row`銆乣hint-chip` 涔嬬被鐨勬柊绫诲悕锛孋SS 瑕佸悓姝ヨˉ榻愶紱鍚﹀垯椤甸潰浼氬嚭鐜扳€滃姛鑳藉凡鎺ヤ笂浣嗚瑙夎８濂斺€濈殑鍋囧畬鎴愮姸鎬併€?- 绉诲姩绔獟浣撴煡璇篃瑕佹妸 builder 鏍呮牸涓€璧锋敼鎴愬崟鍒楋紝鍚﹀垯妗岄潰姝ｅ父銆佹墜鏈烘尋鍧忋€?
4. FastAPI 妯℃澘娓叉煋灞?- 鍦ㄥ綋鍓?Starlette/FastAPI 缁勫悎涓嬶紝`TemplateResponse` 搴斾紭鍏堜娇鐢細

```python
return templates.TemplateResponse(
    request,
    "index.html",
    {"default_api_key_configured": bool(_default_api_key())},
)
```

- 濡傛灉鎶?`request` 鏀捐繘 context dict 鍐嶆寜鏃ч『搴忎紶鍙傦紝娴嬭瘯閲屽彲鑳借Е鍙?`TypeError: unhashable type: 'dict'` 涔嬬被鐨勬ā鏉垮姞杞介敊璇€?
5. 娴嬭瘯灞?- 闄や簡娴?`/api/prompt-builder` 鐨?JSON 杩斿洖锛岃繕瑕佽ˉ涓や釜杞婚噺闆嗘垚娴嬭瘯锛?  - 棣栭〉 HTML 鏄惁鍖呭惈 builder 鍏抽敭 id 鍜屾枃妗?  - 鍓嶇鑴氭湰鏄惁鐪熺殑鍖呭惈 `builder-form`銆乣/api/prompt-builder`銆乣apply-prompt-btn` 绛夊叧閿寕閽?- 杩欐牱鑳芥彁鍓嶅彂鐜扳€滃悗绔湁鎺ュ彛锛屼絾鍓嶇娌℃帴涓娾€濇垨鈥滄ā鏉挎敼浜嗭紝鑴氭湰閫夋嫨鍣ㄥけ鏁堚€濈殑闂銆?

## 鍙傝€冩枃妗?
- GPT-Image-2 鍥剧墖鐢熸垚: `https://docs.aireiter.com/zh/api-reference/images/gpt-image-2/generation`
- 鑾峰彇浠诲姟鐘舵€? `https://docs.aireiter.com/zh/api-reference/tasks/status`

