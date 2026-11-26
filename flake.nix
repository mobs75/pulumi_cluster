{
  description = "pulumi_cluster - toolchain riproducibile (Task, Pulumi, kubectl, Helm) per il cluster MicroK8s su Multipass";

  inputs = {
    # Toolchain principale (go-task, pulumi, helm, jq, yq, python).
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    # Canale separato solo per kubectl: deve restare allineato (skew +/-1) alla
    # versione Kubernetes del cluster (MicroK8s 1.33/stable, come OpenServerless).
    nixpkgs-k8s.url = "github:NixOS/nixpkgs/nixos-25.05";
  };

  outputs = { self, nixpkgs, nixpkgs-k8s }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f {
        pkgs = import nixpkgs { inherit system; };
        k8sPkgs = import nixpkgs-k8s { inherit system; };
      });
    in
    {
      devShells = forAllSystems ({ pkgs, k8sPkgs }: {
        default = pkgs.mkShell {
          packages = [
            pkgs.go-task          # interfaccia operativa (task ...)
            # CLI Pulumi + language host Python fissati da Nix. I plugin dei provider
            # (es. "command") sono fissati a versione esatta in requirements.txt.
            (pkgs.pulumi.withPackages (ps: [ ps.pulumi-python ]))
            pkgs.python312        # runtime del programma Pulumi (Pulumi.yaml: runtime python)
            k8sPkgs.kubectl       # 1.33.x, allineato al cluster
            pkgs.kubernetes-helm  # deploy piattaforma/applicazioni
            pkgs.jq
            pkgs.yq-go
            pkgs.openssh          # ssh-keygen / accesso ai nodi
          ];
          # Le wheel binarie installate da 'pulumi install' nel venv (es. grpcio)
          # richiedono libstdc++/zlib, che il Python di Nix non trova da solo.
          LD_LIBRARY_PATH = pkgs.lib.optionalString pkgs.stdenv.isLinux
            (pkgs.lib.makeLibraryPath [ pkgs.stdenv.cc.cc.lib pkgs.zlib ]);
          # Multipass NON e' fornito da Nix: e' un demone di sistema
          # (snap su Linux, brew/pkg su macOS) e va installato sull'host.
          shellHook = ''
            export PULUMI_SKIP_UPDATE_CHECK=true
            if ! command -v multipass >/dev/null 2>&1; then
              echo "attenzione: 'multipass' non trovato nel PATH (prerequisito dell'host)" >&2
            fi
            echo "pulumi_cluster toolchain pronta. Esegui 'task' per l'elenco dei comandi."
          '';
        };
      });

      formatter = forAllSystems ({ pkgs, ... }: pkgs.nixpkgs-fmt);
    };
}
