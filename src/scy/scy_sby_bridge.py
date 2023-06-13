import os

class SBYBridge():
    def __init__(self, data: "dict[str, list[str]]" = {}):
        self.data = data

    def add_section(self, name: str, contents: "str | list[str]"):
        if isinstance(contents, str):
            contents = contents.splitlines()
        self.data[name] = contents

    @property
    def options(self):
        return self.data["options"]

    @options.setter
    def options(self, contents: "str | list[str]"):
        self.add_section("options", contents)

    @property
    def script(self):
        return self.data["script"]

    @script.setter
    def script(self, contents: "str | list[str]"):
        self.add_section("script", contents)

    @property
    def files(self):
        return self.data["files"]

    @files.setter
    def files(self, contents: "str | list[str]"):
        self.add_section("files", contents)

    def fix_relative_paths(self, dir_prepend: str):
        if self.data["files"]:
            for i, s in enumerate(self.files):
                if s and not os.path.isabs(s):
                    self.files[i] = os.path.join(dir_prepend, s)

    def dump(self, sbyfile, skip_sections: "list[str]" = []):
        for (name, body) in self.data.items():
            if name in skip_sections:
                continue
            print(f"[{name}]", file=sbyfile)
            print("\n".join(body), file=sbyfile)

    def dump_common(self, sbyfile):
        old_options = self.data.get("options")
        options = old_options.copy()
        options.append("mode prep")
        self.options = options
        self.dump(sbyfile, skip_sections=["engines"])
        if old_options:
            self.options = old_options
        else:
            self.data.pop("options")

    def prep_shared(self, common_il: str):
        shared_options = ["mode cover", 
                          "expect pass",
                          "skip_prep on"]
        try:
            self.options.extend(shared_options)
        except KeyError:
            self.options = shared_options
        self.script = ["read_rtlil common_design.il"]
        self.files = [f"common_design.il {common_il}"]
        for key in list(self.data.keys()):
            if "file " in key:
                self.data.pop(key)
