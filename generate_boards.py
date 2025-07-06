# Generate the boards.yaml using the boards.yaml.j2 template

import argparse

from jinja2 import Environment, FileSystemLoader

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="generate_boards")
    parser.add_argument(
        "--qemu-number", default=64, type=int, help="QEMU device number"
    )
    parser.add_argument(
        "--output-file", default="boards.yaml", type=str, help="Output YAML file"
    )

    args = parser.parse_args()

    env = Environment(loader=FileSystemLoader(searchpath="."))
    template = env.get_template("boards.yaml.j2")
    rendered_yaml = template.render({"number": args.qemu_number})
    with open(args.output_file, "w") as f:
        f.write(rendered_yaml)
