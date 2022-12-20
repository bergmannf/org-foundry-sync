;;; Directory Local Variables
;;; For more information see (info "(emacs) Directory Variables")

((python-mode . ((eval . (setq lsp-pylsp-plugins-jedi-environment
                               (car
                                (split-string
                                 (shell-command-to-string "poetry env list --full-path | grep -i activated") " ")))))))
