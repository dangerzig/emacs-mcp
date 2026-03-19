;;; emacs-mcp-bridge.el --- TCP server for the emacs-mcp MCP bridge  -*- lexical-binding: t -*-

;; Author: Dan Zigmond <djz@shmonk.com>
;; URL: https://github.com/dangerzig/emacs-mcp
;; Version: 0.1.0
;; Package-Requires: ((emacs "27.1"))

;;; Commentary:

;; A lightweight TCP server that lets the emacs-mcp Python MCP server
;; talk to Emacs over a persistent connection.  Add this file to your
;; load-path and (require 'emacs-mcp-bridge), or copy the code into
;; your init.el.
;;
;; The server listens on 127.0.0.1:9377 and speaks newline-delimited
;; JSON.  It handles these methods:
;;
;;   eval             - evaluate arbitrary Elisp
;;   list_buffers     - list open buffers
;;   get_buffer_content - read a buffer's text
;;   open_file        - open a file in a new frame
;;   insert_scratch   - insert text into *scratch*
;;   save_buffer      - save a buffer
;;   get_selection    - get the active region
;;
;; Start with M-x emacs-mcp-start or (emacs-mcp-start).
;; Stop with M-x emacs-mcp-stop.

;;; Code:

(require 'json)
(require 'seq)

(defvar emacs-mcp-port 9377
  "TCP port for the Emacs MCP bridge server.")

(defvar emacs-mcp-server-process nil
  "The network server process for MCP bridge.")

(defvar emacs-mcp--partial-input (make-hash-table :test 'eq)
  "Partial input buffer per client connection, keyed by process.")

(defun emacs-mcp--user-window ()
  "Return the window the user is actually editing in.
During a process filter the selected window may be a minibuffer;
`minibuffer-selected-window' gives the real editing window."
  (or (minibuffer-selected-window) (selected-window)))

(defun emacs-mcp--handle-request (request)
  "Handle a single JSON REQUEST and return a response alist."
  (let* ((method (gethash "method" request))
         (params (gethash "params" request))
         (id (gethash "id" request)))
    (condition-case err
        (let ((result
               (pcase method
                 ("eval"
                  `((value . ,(format "%S"
                                      (eval (car (read-from-string
                                                  (gethash "expression" params))))))))
                 ("get_buffer_content"
                  (let* ((name (gethash "buffer" params))
                         (buf (get-buffer name)))
                    (if buf
                        `((content . ,(with-current-buffer buf
                                        (buffer-substring-no-properties
                                         (point-min) (point-max)))))
                      `((error . ,(format "Buffer %s not found" name))))))
                 ("list_buffers"
                  `((buffers . ,(vconcat
                                 (mapcar (lambda (b)
                                           `((name . ,(buffer-name b))
                                             (file . ,(or (buffer-file-name b) :null))
                                             (modified . ,(if (buffer-modified-p b) t :false))))
                                         (seq-filter
                                          (lambda (b)
                                            (not (string-prefix-p " " (buffer-name b))))
                                          (buffer-list)))))))
                 ("open_file"
                  (let ((path (gethash "path" params))
                        (line (gethash "line" params)))
                    (find-file-other-frame path)
                    (when line (goto-char (point-min)) (forward-line (1- line)))
                    `((opened . ,path))))
                 ("insert_scratch"
                  (let ((text (gethash "text" params)))
                    (let ((win (get-buffer-window "*scratch*" t)))
                      (if win
                          (select-frame-set-input-focus (window-frame win))
                        (switch-to-buffer-other-frame "*scratch*")))
                    (with-current-buffer "*scratch*"
                      (erase-buffer)
                      (insert text))
                    `((inserted . t))))
                 ("save_buffer"
                  (let* ((name (gethash "buffer" params))
                         (buf (if name
                                  (get-buffer name)
                                (window-buffer (emacs-mcp--user-window)))))
                    (cond
                     ((not buf)
                      `((error . "Buffer not found")))
                     ((not (buffer-file-name buf))
                      `((error . ,(format "Buffer %s has no file" (buffer-name buf)))))
                     (t
                      (with-current-buffer buf
                        (save-buffer)
                        `((saved . ,(buffer-name buf))))))))
                 ("get_selection"
                  (with-current-buffer (window-buffer (emacs-mcp--user-window))
                    (if (use-region-p)
                        `((selection . ,(buffer-substring-no-properties
                                         (region-beginning) (region-end))))
                      `((selection . :null)))))
                 (_
                  `((error . ,(format "Unknown method: %s" method)))))))
          `((id . ,id) (result . ,result)))
      (error
       `((id . ,id) (error . ((message . ,(error-message-string err)))))))))

(defun emacs-mcp--process-filter (proc input)
  "Accumulate INPUT from PROC until a complete newline-delimited JSON message arrives."
  (let ((existing (gethash proc emacs-mcp--partial-input "")))
    (setq existing (concat existing input))
    (while (string-match "\n" existing)
      (let* ((pos (match-end 0))
             (line (substring existing 0 (1- pos))))
        (setq existing (substring existing pos))
        (when (> (length line) 0)
          (condition-case err
              (let* ((request (json-parse-string line))
                     (response (emacs-mcp--handle-request request))
                     (json-out (json-serialize response)))
                (process-send-string proc (concat json-out "\n")))
            (error
             (let ((err-response (json-serialize
                                  `((id . nil)
                                    (error . ((message . ,(error-message-string err))))))))
               (process-send-string proc (concat err-response "\n"))))))))
    (puthash proc existing emacs-mcp--partial-input)))

(defun emacs-mcp--sentinel (proc event)
  "Clean up when a client disconnects."
  (when (string-match "\\(closed\\|broken\\|deleted\\)" event)
    (remhash proc emacs-mcp--partial-input)))

;;;###autoload
(defun emacs-mcp-start ()
  "Start the MCP bridge TCP server."
  (interactive)
  (when (and emacs-mcp-server-process
             (process-live-p emacs-mcp-server-process))
    (delete-process emacs-mcp-server-process))
  (setq emacs-mcp-server-process
        (make-network-process
         :name "emacs-mcp-bridge"
         :server t
         :host "127.0.0.1"
         :service emacs-mcp-port
         :family 'ipv4
         :filter #'emacs-mcp--process-filter
         :sentinel #'emacs-mcp--sentinel
         :noquery t))
  (message "MCP bridge server started on port %d" emacs-mcp-port))

;;;###autoload
(defun emacs-mcp-stop ()
  "Stop the MCP bridge TCP server."
  (interactive)
  (when emacs-mcp-server-process
    (when (process-live-p emacs-mcp-server-process)
      (delete-process emacs-mcp-server-process))
    (setq emacs-mcp-server-process nil)
    (clrhash emacs-mcp--partial-input)
    (message "MCP bridge server stopped")))

(provide 'emacs-mcp-bridge)
;;; emacs-mcp-bridge.el ends here
