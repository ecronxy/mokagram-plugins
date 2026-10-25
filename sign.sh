#!/usr/bin/env bash
# Пересобирает index.json из plugins/*.plugin и подписывает его ключом mokaGram.
# Ключ: ~/.config/mokagram/update-key.pem (или MOKAGRAM_UPDATE_KEY). Запуск из корня репозитория.
set -euo pipefail
key=${MOKAGRAM_UPDATE_KEY:-$HOME/.config/mokagram/update-key.pem}
[[ -f "$key" ]] || { echo "Нет ключа $key" >&2; exit 1; }
python3 - <<'PY' > index.json
import glob, hashlib, json, os, re
out = []
for path in sorted(glob.glob("plugins/*.plugin")):
    data = open(path, "rb").read()
    src = data.decode("utf-8")
    def field(name):
        m = re.search(r'^__%s__\s*=\s*(.+)$' % name, src, re.M)
        return eval(m.group(1), {}) if m else ""
    out.append({
        "id": field("id"), "name": field("name"),
        "description": field("description"), "author": field("author"),
        "version": field("version"), "icon": field("icon"), "permissions": field("permissions") or [],
        "file": os.path.basename(path),
        "sha256": hashlib.sha256(data).hexdigest(), "size": len(data),
    })
print(json.dumps({"plugins": out}, ensure_ascii=False, indent=2))
PY
# Файлы плагинов лежат в корне рядом с index.json: клиент берёт их по имени.
cp plugins/*.plugin .
{ printf 'mokagram-plugins\n'; cat index.json; } > /tmp/.mp_msg
openssl pkeyutl -sign -rawin -inkey "$key" -in /tmp/.mp_msg | base64 -w0 > index.json.sig
rm -f /tmp/.mp_msg
echo "Готово: $(grep -c '"id"' index.json) плагинов"
