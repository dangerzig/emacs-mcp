;;; claude-sessions.el --- Named Claude Code sessions in Emacs vterm  -*- lexical-binding: t; -*-

;; Copyright (C) 2026 Dan Zigmond
;; Author: Dan Zigmond <djz@shmonk.com>
;; URL: https://github.com/dangerzig/emacs-mcp
;; Package-Requires: ((emacs "27.1") (vterm "0.0.1"))
;; SPDX-License-Identifier: MIT

;;; Commentary:

;; Companion to the emacs-mcp bridge: convenience commands for running
;; Claude Code (the CLI) inside Emacs `vterm' buffers.
;;
;; The problem it solves: if you keep many Claude sessions open in vterm
;; buffers and Emacs dies (or you quit), the live `claude' processes are
;; killed.  The conversations themselves are never lost (Claude Code writes
;; a JSONL transcript per session under ~/.claude/projects/), but matching an
;; opaque session UUID back to "the buffer I called `email'" is painful.
;;
;; This file fixes that by recording, at launch time, a mapping of
;;   name  ->  session-id  ->  directory
;; in a small TSV registry.  New sessions get a pre-minted session id (via
;; `claude --session-id'), so after any crash you reopen a session BY NAME
;; and it resumes exactly where it stopped.
;;
;; It also adds a compose buffer: the live vterm prompt sends keystrokes
;; straight to Claude, so Emacs editing commands (transpose-chars, kill-ring,
;; flyspell, ...) can't touch that line in place.  `C-c e' pops a real
;; text-mode buffer where you edit with full Emacs power, then ships the text
;; to the session as a bracketed paste.
;;
;; Key bindings:
;;   C-c c n  new NAMED session in its own frame  (the default way to start)
;;   C-c c r  reopen a registered session by name (the default way to restart)
;;   C-c c R  claude --continue (most recent; rarely useful with many sessions)
;;   C-c c c  new unnamed session in the current window
;;   C-c e    (in a claude-* buffer) open the compose buffer
;;              C-c C-c  send + submit    C-c C-k  cancel
;;
;; Usage: put this file on your `load-path' and (require 'claude-sessions).

;;; Code:

(declare-function vterm "ext:vterm")
(declare-function vterm-send-string "ext:vterm")
(declare-function vterm-send-return "ext:vterm")
(defvar vterm-shell)
(defvar vterm-mode-map)

(defgroup claude-sessions nil
  "Run named Claude Code sessions in vterm."
  :group 'tools)

(defcustom claude-session-registry (expand-file-name "~/.claude/vterm-sessions.tsv")
  "TSV log of Claude vterm sessions: name<TAB>session-id<TAB>dir<TAB>timestamp."
  :type 'file
  :group 'claude-sessions)

;;;; Starting and restarting sessions

;;;###autoload
(defun my/claude-code ()
  "Start Claude Code in a vterm buffer (unnamed, in the current window)."
  (interactive)
  (let ((vterm-shell "claude"))
    (vterm)))

;;;###autoload
(defun my/claude-code-resume ()
  "Resume the most recent Claude Code conversation (\"claude --continue\")."
  (interactive)
  (let ((vterm-shell "claude --continue"))
    (vterm)))

;;;###autoload
(defun my/claude-new-frame (name)
  "Open a fresh, named Claude Code session in a new frame.
Starts Claude with a pre-minted session id and records NAME in
`claude-session-registry' so the session can be reopened by name later."
  (interactive (list (read-string "Claude session name: ")))
  (let* ((id (downcase (string-trim (shell-command-to-string "uuidgen"))))
         (label (if (string-empty-p name) id name))
         (buf-name (format "claude-%s" label))
         ;; Always start new sessions in HOME, not the current buffer's dir,
         ;; so the session's project/cwd is predictable (see git log for why).
         (default-directory (expand-file-name "~/"))
         (dir default-directory)
         (frame (make-frame))
         (vterm-shell (format "claude --session-id %s" id)))
    (append-to-file
     (format "%s\t%s\t%s\t%s\n" label id dir (format-time-string "%Y-%m-%d %H:%M"))
     nil claude-session-registry)
    (select-frame-set-input-focus frame)
    (vterm buf-name)))

;;;###autoload
(defun my/claude-resume-named ()
  "Reopen a registered Claude session by name in a fresh frame."
  (interactive)
  (let* ((rows (when (file-exists-p claude-session-registry)
                 (with-temp-buffer
                   (insert-file-contents claude-session-registry)
                   (nreverse (split-string (buffer-string) "\n" t)))))  ; newest first
         (alist (mapcar (lambda (l) (let ((f (split-string l "\t"))) (cons (car f) f)))
                        rows))
         (name (completing-read "Resume Claude session: " alist nil t))
         (row (cdr (assoc name alist)))
         (default-directory (or (nth 2 row) default-directory))
         (frame (make-frame))
         (vterm-shell (format "claude --resume %s" (nth 1 row))))
    (select-frame-set-input-focus frame)
    (vterm (format "claude-%s" name))))

;;;; Compose buffer

(defvar-local my/claude-compose-target nil
  "The vterm buffer a `*claude-compose*' buffer sends to.")

;;;###autoload
(defun my/claude-compose ()
  "Pop a text buffer to compose a message for the current Claude session."
  (interactive)
  (let ((target (current-buffer))
        (buf (get-buffer-create "*claude-compose*")))
    (with-current-buffer buf
      (erase-buffer)
      (text-mode)
      (setq my/claude-compose-target target)
      (setq header-line-format
            "Compose for Claude  —  C-c C-c send · C-c C-k cancel")
      (local-set-key (kbd "C-c C-c") #'my/claude-compose-send)
      (local-set-key (kbd "C-c C-k") #'my/claude-compose-cancel))
    (pop-to-buffer buf)))

(defun my/claude-compose-send ()
  "Send the compose buffer to its Claude session as a paste, then submit."
  (interactive)
  (let ((text (string-trim-right (buffer-string)))
        (target my/claude-compose-target))
    (if (buffer-live-p target)
        (progn
          (with-current-buffer target
            (vterm-send-string text t)   ; t = bracketed paste (keeps newlines)
            (vterm-send-return))
          (my/claude-compose-cancel)
          (pop-to-buffer target))
      (message "Claude session buffer is gone; not sent."))))

(defun my/claude-compose-cancel ()
  "Close the compose buffer without sending."
  (interactive)
  (let ((w (get-buffer-window "*claude-compose*")))
    (when (buffer-live-p (get-buffer "*claude-compose*"))
      (kill-buffer "*claude-compose*"))
    (when (window-live-p w) (ignore-errors (delete-window w)))))

;;;; Key bindings

(global-set-key (kbd "C-c c c") 'my/claude-code)          ; new unnamed session
(global-set-key (kbd "C-c c n") 'my/claude-new-frame)     ; new named session
(global-set-key (kbd "C-c c r") 'my/claude-resume-named)  ; reopen by name (the one to use)
(global-set-key (kbd "C-c c R") 'my/claude-code-resume)   ; claude --continue (rarely useful)

;; C-c e in any vterm opens the compose buffer.
(with-eval-after-load 'vterm
  (define-key vterm-mode-map (kbd "C-c e") #'my/claude-compose))

(provide 'claude-sessions)

;;; claude-sessions.el ends here
