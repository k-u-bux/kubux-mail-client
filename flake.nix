{
  description = "A Notmuch email client with predictive pre-tagging";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.05";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        pythonEnv = pkgs.python3.withPackages (pyPkgs: [
          pyPkgs.pyside6
          pyPkgs.notmuch
          pyPkgs.scikit-learn
          pyPkgs.toml
          pyPkgs.imapclient
          pyPkgs.watchdog
          pyPkgs.mail-parser
          pyPkgs.pytest
          pyPkgs.scancode-toolkit
        ]);
      in {
        packages.default = pkgs.stdenv.mkDerivation {
          pname = "kubux-mail-client";
          version = "0.1";
          
          src = ./.;
          
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
            pkgs.jq
            pkgs.imagemagick 
          ];
          nativeBuildInputs = [ 
            pkgs.makeWrapper
            pythonEnv
            pkgs.notmuch
            pkgs.muchsync
            pkgs.isync
            pkgs.gnupg
            pkgs.msmtp
          ];

          installPhase = ''
            mkdir -p $out/bin
            mkdir -p $out/share/applications
	          mkdir -p $out/share/man/man1
	    
            # Copy the Python scripts
            cp $src/scripts/*.py $out/bin/
            cp $src/scripts/*.jq $out/bin/
            cp $src/scripts/predict-tags $out/bin/
            cp $src/scripts/decrypt-on-the-fly $out/bin/
            cp $src/scripts/mbsync-and-decrypt $out/bin/
            chmod +x $out/bin/*.py
            # chmod +x $out/bin/*.sh
            chmod +x $out/bin/predict-tags
            chmod +x $out/bin/decrypt-on-the-fly
            chmod +x $out/bin/mbsync-and-decrypt

	          # Copy the man page
	          # cp kubux-mail-client.1 $out/share/man/man1

            # Create wrapper using makeWrapper for proper desktop integration
            for file in ai-classify ai-train edit-mail view-mail view-thread open-drafts manage-mail show-query-results send-mail get-message-id pause-imap-sync; do
              makeWrapper ${pythonEnv}/bin/python $out/bin/$file \
                --add-flags "$out/bin/$file.py" \
                --set-default TMPDIR "/tmp";
	          done
    
            # Copy desktop file
            cp kubux-mail-client.desktop $out/share/applications/

            # Make icons for all sizes
            for size in 16x16 22x22 24x24 32x32 48x48 64x64 96x96 128x128 192x192 256x256; do
 	            mkdir -p $out/share/icons/hicolor/$size/apps
	            magick convert $src/app-icon.png -resize $size $out/share/icons/hicolor/$size/apps/kubux-mail-client.png
            done
          '';
          
          meta = with pkgs.lib; {
            description = "A Notmuch email client with predictive pre-tagging";
            homepage = "https://github.com/kubux/kubux-mail-client";
            license = licenses.asl20;
            maintainers = [ ];
            platforms = platforms.linux;
          };
        };

        devShells.default = pkgs.mkShell {
          buildInputs = [
            pythonEnv
            pkgs.isync
            pkgs.poetry
            pkgs.black
            pkgs.isort
            pkgs.mypy
            pkgs.notmuch
            pkgs.muchsync
            pkgs.gnupg
            pkgs.msmtp
            pkgs.jq
          ];
    
          shellHook = ''
            echo "Welcome to the kubux-notmuch-mail-client development shell!"
            echo "Python environment is ready with PySide6, Notmuch, Scikit-learn, and TOML."
            echo "System tools like notmuch, mbsync, gpg, and msmtp are also available."
            export KUBUIX_NOTMUCH_CONFIG_DIR=$HOME/.config/kubux-notmuch-mail-client
          '';
        };
      });   
}