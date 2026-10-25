#!/usr/bin/env python3
"""Проверка плагинов перед подписью каталога. Отклоняет приёмы, которыми в чужие плагины
дописывают вредоносную вставку: зашифрованный код, exec/eval, загрузку и запуск кода из сети.
Запуск: python3 lint.py plugins/*.plugin. Код возврата 1, если что-то нашлось."""
import ast
import re
import sys

BAD_CALLS = {'exec', 'eval', 'compile', '__import__', 'marshal', 'pickle', 'ctypes', 'subprocess', 'os.system',
             'os.popen', 'importlib', 'socket', 'webbrowser'}
BAD_TEXT = [
    (re.compile(r'#\s*=+\s*injected', re.I), 'вставка «injected»'),
    (re.compile(r'b64decode|base64\.|bytes\.fromhex|binascii|codecs\.decode|zlib|lzma|bz2'), 'раскодирование данных'),
    (re.compile(r'\^\s*_?k\[|c\s*\^\s*k'), 'XOR-шифрование'),
    (re.compile(r'urllib|requests|http\.client|urlopen'), 'прямой выход в сеть (используйте api.http с правом network)'),
]


def names(node):
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            out.append(n.id)
        elif isinstance(n, ast.Attribute):
            parts, cur = [], n
            while isinstance(cur, ast.Attribute):
                parts.append(cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name):
                parts.append(cur.id)
                out.append('.'.join(reversed(parts)))
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                out.append((getattr(n, 'module', None) or a.name).split('.')[0])
    return out


def check(path):
    src = open(path, encoding='utf-8').read()
    problems = []
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return ['синтаксис: %s' % e]
    used = set(names(tree))
    for bad in sorted(BAD_CALLS & used):
        problems.append('запрещено: %s' % bad)
    for rx, why in BAD_TEXT:
        if rx.search(src):
            problems.append(why)
    if len(src) > 200_000:
        problems.append('файл слишком большой')
    if re.search(r'[A-Za-z0-9+/=]{300,}', src):
        problems.append('длинная строка base64')
    return problems


if __name__ == '__main__':
    bad = 0
    for p in sys.argv[1:]:
        for why in check(p):
            print('%s: %s' % (p, why))
            bad = 1
    sys.exit(bad)
