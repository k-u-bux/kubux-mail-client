{
  description = "A Notmuch email client with AI pre-tagging";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.05";
  };

  outputs = { self, nixpkgs }: let
    system = "x86_64-linux";
    pkgs = nixpkgs.legacyPackages.${system};
    pythonEnv = pkgs.python3.withPackages (pyPkgs: [
      pyPkgs.pyside6
      pyPkgs.notmuch
      pyPkgs.scikit-learn
      pyPkgs.toml
      pyPkgs.pytest
    ]);
  in {
    apps.kubux-notmuch-mail-client = {
      type = "app";
      program = "${self.packages.${system}.kubux-notmuch-mail-client}/bin/kubux-notmuch-mail-client";
    };

    packages.${system}.kubux-notmuch-mail-client = pkgs.python3Packages.buildPythonApplication rec {
      pname = "kubux-notmuch-mail-client";
      version = "0.1.0";

      src = ./.;

      buildInputs = [
        pythonEnv
        pkgs.notmuch
        pkgs.isync
        pkgs.gnupg
        pkgs.msmtp
      ];
      
      installPhase = ''
        runHook preInstall
        mkdir -p $out/lib/${pname}
        cp -r core_library $out/lib/${pname}/
      '';
    };

    devShell.${system} = pkgs.mkShell {
      buildInputs = [
        pythonEnv
        pkgs.isync
        pkgs.poetry
        pkgs.black
        pkgs.isort
        pkgs.mypy
        pkgs.notmuch
        pkgs.gnupg
        pkgs.msmtp
      ];

      shellHook = ''
        echo "Welcome to the kubux-notmuch-mail-client development shell!"
        echo "Python environment is ready with PySide6, Notmuch, Scikit-learn, and TOML."
        echo "System tools like notmuch, mbsync, gpg, and msmtp are also available."
        export KUBUIX_NOTMUCH_CONFIG_DIR=$HOME/.config/kubux-notmuch-mail-client
      '';
    };
  };
}