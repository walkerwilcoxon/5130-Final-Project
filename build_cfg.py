
import sys
from scalpel.cfg import CFGBuilder


def main(): 
    name = sys.argv[1] if len(sys.argv) > 1 else 'json_parser.py'
    cfg = CFGBuilder().build_from_file(name, f'./{name}')

    dot = cfg.build_visual('png')
    dot.render('./diagram', view=False)

    for (_, func_name), func_cfg in cfg.functioncfgs.items():
        dot = func_cfg.build_visual('png')
        dot.render(f'cfg/{name[:-3]}/{func_name}', view=False)
        
if __name__ == "__main__":
    main()
