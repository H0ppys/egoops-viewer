"""把「广东省湛江市赤坎区人民大道88号」这种整串地址，拆成 省 / 市 / 区 / 街道门牌号。

数据：pca.json（省-市-区，110KB，随查看器一起打包）
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CANDIDATES = [
    os.path.join(HERE, "pca.json"),
    os.path.join(getattr(__import__("sys"), "_MEIPASS", HERE), "pca.json"),
]

_PCA = None


def load():
    global _PCA
    if _PCA is not None:
        return _PCA
    for p in CANDIDATES:
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                _PCA = json.load(f)
            return _PCA
    _PCA = []
    return _PCA


def _norm(s):
    return (s or "").replace(" ", "").replace("　", "")


def parse(address):
    """返回 dict(province, city, district, street, ok, note)"""
    text = _norm(address)
    out = {"province": "", "city": "", "district": "", "street": text, "ok": False, "note": ""}
    if not text:
        out["note"] = "地址为空"
        return out

    for prov in load():
        pname = prov["name"]
        short = pname.replace("省", "").replace("市", "").replace("自治区", "").replace("壮族", "") \
                    .replace("回族", "").replace("维吾尔", "")
        if text.startswith(pname) or text.startswith(short):
            out["province"] = pname
            rest = text[len(pname):] if text.startswith(pname) else text[len(short):]
            for city in prov.get("children") or []:
                cname = city["name"]
                cshort = cname.replace("市", "").replace("地区", "").replace("自治州", "")
                if rest.startswith(cname) or rest.startswith(cshort):
                    out["city"] = cname
                    rest2 = rest[len(cname):] if rest.startswith(cname) else rest[len(cshort):]
                    for dist in city.get("children") or []:
                        dname = dist["name"]
                        dshort = dname.replace("区", "").replace("县", "").replace("市", "")
                        if rest2.startswith(dname) or (dshort and rest2.startswith(dshort)):
                            out["district"] = dname
                            out["street"] = rest2[len(dname):] if rest2.startswith(dname) else rest2[len(dshort):]
                            break
                    if not out["district"]:
                        out["street"] = rest2
                    break
            if not out["city"]:
                # 直辖市 / 省掉市名：直接在这个省的所有区县里找
                for city in prov.get("children") or []:
                    for dist in city.get("children") or []:
                        dname = dist["name"]
                        dshort = dname.replace("区", "").replace("县", "").replace("市", "")
                        if rest.startswith(dname) or (dshort and rest.startswith(dshort)):
                            out["city"] = city["name"]
                            out["district"] = dname
                            out["street"] = rest[len(dname):] if rest.startswith(dname) else rest[len(dshort):]
                            break
                    if out["district"]:
                        break
                if not out["district"]:
                    out["street"] = rest
            break

    out["ok"] = bool(out["province"] and out["city"] and out["district"])
    if not out["province"]:
        out["note"] = "没匹配到省份"
    elif not out["city"]:
        out["note"] = "匹配到省，没匹配到市"
    elif not out["district"]:
        out["note"] = "匹配到省市，没匹配到区县"
    return out


if __name__ == "__main__":
    for a in [
        "广东省湛江市赤坎区人民大道88号",
        "江西省南昌市东湖区新村11号",
        "广东湛江赤坎区人民大道88号",
        "河北省保定市恒祥北大街假日山水园",
        "北京市朝阳区望京SOHO T1",
    ]:
        print(a, "->", json.dumps(parse(a), ensure_ascii=False))
