{
  description = "A Notmuch email client with AI pre-tagging";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-25.05";
  };

  outputs = { self, nixpkgs }: let
    system = "x86_64-linux"; # Assuming Linux, can be made configurable
    pkgs = nixpkgs.legacyPackages.${system};
    pythonEnv = pkgs.python3.withPackages (pyPkgs: with pyPkgs; [
      pyside6
      notmuch
      notmuch2
      scikit-learn
      toml # For config file parsing
    ]);
  in {
    # Define the application itself
    apps.kubux-notmuch-mail-client = {
      type = "app";
      program = "${self.packages.${system}.kubux-notmuch-mail-client}/bin/kubux-notmuch-mail-client";
    };

    # Define the default package for `nix build`
    packages.${system}.kubux-notmuch-mail-client = pkgs.python3Packages.buildPythonApplication {
      pname = "kubux-notmuch-mail-client";
      version = "0.1.0"; # Initial version

      src = ./.; # Assumes your project source is in the current directory

      # Python dependencies
      buildInputs = [
        pythonEnv
        # System dependencies that the Python app interacts with at runtime
        pkgs.notmuch
        pkgs.gnupg # For gpg
        pkgs.msmtp # For sending mail
      ];

      # This is a placeholder. You'd replace this with your actual build/installation steps.
      # For a simple Python app, this might just involve copying scripts and setting up entry points.
      # For now, let's create a dummy entry point script.
      postInstall = ''
        mkdir -p $out/bin
        # Assuming your main entry point for the GUI is `main.py`
        # and the individual GUI components will be launched from it,
        # or have their own wrappers.
        # This creates a simple wrapper script for the main application.
        echo '#!${pkgs.stdenv.shell}' > $out/bin/kubux-notmuch-mail-client
        echo 'exec ${pythonEnv}/bin/python ${./main.py}' >> $out/bin/kubux-notmuch-mail-client
        chmod +x $out/bin/kubux-notmuch-mail-client

        # You might also want to copy the background service scripts and make them executable
        # mkdir -p $out/lib/kubux-notmuch-mail-client/scripts
        # cp ./ai_classifier.py $out/lib/kubux-notmuch-mail-client/scripts/
        # chmod +x $out/lib/kubux-notmuch-mail-client/scripts/ai_classifier.py
        # etc.
      '';
    };

    # Define a development shell for working on the project
    devShell.${system} = pkgs.mkShell {
      # This ensures all Python packages are available in the shell
      # and the Python interpreter itself.
      buildInputs = [
        pythonEnv

        # General development tools
        pkgs.poetry # If you manage Python dependencies with Poetry
        pkgs.black # Code formatter
        pkgs.isort # Import sorter
        pkgs.mypy # Type checker
        # pkgs.pytest # Testing framework

        # System dependencies for development/testing
        pkgs.notmuch
        pkgs.gnupg
        pkgs.msmtp
      ];

      # Environment variables specific to your project, e.g., for testing
      shellHook = ''
        echo "Welcome to the kubux-notmuch-mail-client development shell!"
        echo "Python environment is ready with PySide6, Notmuch, Scikit-learn, and TOML."
        echo "System tools like notmuch, gpg, and msmtp are also available."
        # Optionally, set environment variables for your application's paths if needed during dev
        export KUBUIX_NOTMUCH_CONFIG_DIR=$HOME/.config/kubux-notmuch-mail-client
      '';
    };
  };
}