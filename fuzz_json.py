import sys
import atheris


with atheris.instrument_imports():
    import json_parser  

def TestOneInput(data):
    fdp = atheris.FuzzedDataProvider(data)
    text = fdp.ConsumeUnicode(len(data))
    try:
        json_parser.parse(text)
    except json_parser.JSONParseError:
        pass
    except Exception as e:
        raise


atheris.Setup(sys.argv, TestOneInput)
atheris.Fuzz()
