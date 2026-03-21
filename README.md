HP TOOL ARCHITECTURE

```text
hp_tool/
├── main.py
├── requirements.txt
├── cli.py
├── commands/
│   ├── __init__.py
│   ├── base.py
│   ├── transfer.py
│   ├── build_tgv.py
│   └── build_and_transfer.py
├── conn/
│   ├── __init__.py
│   ├── packet.py
│   ├── session.py             # owns full Kermit orchestration
│   └── transport.py           # sender.py only if Model B/C is decided
├── tgv/
│   ├── __init__.py
│   ├── latex2txt.py           # step 1: LaTeX → plain text
│   ├── inject_vars.py         # step 2: variable injection
│   ├── gen_t49.py             # step 3a: emit .T49 binary
│   └── gen_bmp_model0.py      # step 3b: emit BMP variant
│                              # builder.py only if pipeline logic is complex
└── utils/
    ├── __init__.py
    ├── constants.py
    ├── exceptions.py
    ├── logging.py
    ├── utils.py
    └── charmap.py
```

python main.py --debug build-tgv /home/luis/me/hp50g/latex_model --gen-imgs
python main.py --debug build-tgv /home/luis/me/hp50g/latex_model --txt-file lista1.txt --gen-text --gen-t49
python main.py --debug transfer /home/luis/me/hp50g/latex_model /dev/ttyUSB0
