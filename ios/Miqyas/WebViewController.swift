import UIKit
import WebKit

/// The system itself, full screen, for one company. Everything the system
/// does — CRM, tasks, petty cash, approvals, whatever is built next — arrives
/// here with no new release of the app; this controller only adds what a web
/// page cannot do on a phone by itself.
final class WebViewController: UIViewController, WKNavigationDelegate, WKUIDelegate,
                               WKDownloadDelegate, WKScriptMessageHandler {
    let host: String
    private let start: URL?
    private var webView: WKWebView!
    private let progress = UIProgressView(progressViewStyle: .bar)
    private var progressObservation: NSKeyValueObservation?
    private var errorView: UIView?
    private var registeredToken: String?
    private var askedForNotifications = false
    private var downloads: [WKDownload: URL] = [:]

    init(host: String, start: URL? = nil) {
        self.host = host
        self.start = start
        super.init(nibName: nil, bundle: nil)
    }

    required init?(coder: NSCoder) { fatalError("not used") }

    override var preferredStatusBarStyle: UIStatusBarStyle { .lightContent }

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .brand

        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default()          // stay signed in between launches
        config.allowsInlineMediaPlayback = true
        config.applicationNameForUserAgent = "MiqyasApp/1.0 Mobile"
        config.userContentController.add(WeakHandler(self), name: "miqyas")

        webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.allowsBackForwardNavigationGestures = true
        webView.scrollView.contentInsetAdjustmentBehavior = .never
        webView.isOpaque = false
        webView.backgroundColor = .white
        if #available(iOS 16.4, *) { webView.isInspectable = false }

        let refresh = UIRefreshControl()
        refresh.addTarget(self, action: #selector(reload(_:)), for: .valueChanged)
        webView.scrollView.refreshControl = refresh

        webView.translatesAutoresizingMaskIntoConstraints = false
        progress.translatesAutoresizingMaskIntoConstraints = false
        progress.progressTintColor = UIColor(white: 1, alpha: 0.9)
        progress.trackTintColor = .clear
        view.addSubview(webView)
        view.addSubview(progress)
        NSLayoutConstraint.activate([
            webView.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),
            webView.bottomAnchor.constraint(equalTo: view.bottomAnchor),
            webView.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            webView.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            progress.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),
            progress.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            progress.trailingAnchor.constraint(equalTo: view.trailingAnchor),
        ])
        progressObservation = webView.observe(\.estimatedProgress) { [weak self] web, _ in
            self?.progress.setProgress(Float(web.estimatedProgress), animated: true)
            self?.progress.isHidden = web.estimatedProgress >= 1
        }

        NotificationCenter.default.addObserver(self, selector: #selector(tokenArrived),
                                               name: .miqyasPushToken, object: nil)
        load(start ?? URL(string: "https://\(host)/odoo")!)
    }

    func load(_ url: URL) {
        hideError()
        webView.load(URLRequest(url: url))
    }

    @objc private func reload(_ sender: UIRefreshControl) {
        webView.reload()
        sender.endRefreshing()
    }

    // MARK: navigation

    private func isOurs(_ url: URL) -> Bool {
        guard let urlHost = url.host else { return false }
        let full = url.port.map { "\(urlHost):\($0)" } ?? urlHost
        return full == host
    }

    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = action.request.url, let scheme = url.scheme?.lowercased() else {
            return decisionHandler(.allow)
        }
        if ["tel", "mailto", "sms", "whatsapp", "maps"].contains(scheme) {
            UIApplication.shared.open(url)
            return decisionHandler(.cancel)
        }
        if ["about", "blob", "data"].contains(scheme) { return decisionHandler(.allow) }
        if action.shouldPerformDownload { return decisionHandler(.download) }
        // The company's own pages stay in the app; anything else — a map, a
        // supplier's site — opens in Safari, where it belongs.
        if action.targetFrame?.isMainFrame != false, !isOurs(url) {
            UIApplication.shared.open(url)
            return decisionHandler(.cancel)
        }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, decidePolicyFor response: WKNavigationResponse,
                 decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        let http = response.response as? HTTPURLResponse
        let disposition = (http?.value(forHTTPHeaderField: "Content-Disposition") ?? "").lowercased()
        // Reports, Excel exports, attachments: saved and offered to share or
        // keep in Files, instead of a page with no way back.
        if disposition.hasPrefix("attachment") || !response.canShowMIMEType {
            return decisionHandler(.download)
        }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
        download.delegate = self
    }

    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) {
        download.delegate = self
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        hideError()
        guard let url = webView.url, isOurs(url) else { return }
        let path = url.path
        let signedIn = (path.hasPrefix("/odoo") || path.hasPrefix("/web")) && !path.hasPrefix("/web/login")
            && !path.hasPrefix("/web/reset_password") && !path.hasPrefix("/web/signup")
        guard signedIn else { return }
        if !askedForNotifications {
            askedForNotifications = true
            AppDelegate.shared.askForNotifications()
        }
        registerToken()
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        let code = (error as NSError).code
        if code == NSURLErrorCancelled || code == 102 /* frame load interrupted by a download */ { return }
        showError()
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        let code = (error as NSError).code
        if code == NSURLErrorCancelled || code == 102 { return }
        showError()
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        webView.reload()
    }

    // MARK: notifications token

    @objc private func tokenArrived() { registerToken() }

    /// Hands the phone's token to the server from inside the signed-in page,
    /// so it is filed under whoever is logged in — never under a guess.
    private func registerToken() {
        guard let token = AppDelegate.pushToken, token != registeredToken,
              let url = webView.url, isOurs(url) else { return }
        let bundle = Bundle.main.bundleIdentifier ?? ""
        let script = """
        fetch('/mizan/push/register', {method: 'POST', credentials: 'same-origin',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({jsonrpc: '2.0', method: 'call',
            params: {token: '\(token)', platform: 'ios', app_id: '\(bundle)'}})})
        .then(r => r.json())
        .then(j => window.webkit.messageHandlers.miqyas.postMessage({registered: !!(j.result && j.result.ok)}))
        .catch(() => {});
        """
        webView.evaluateJavaScript(script)
    }

    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
        if let body = message.body as? [String: Any], body["registered"] as? Bool == true {
            registeredToken = AppDelegate.pushToken
        }
    }

    // MARK: windows, dialogs, camera

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = action.request.url {
            if isOurs(url) { webView.load(action.request) } else { UIApplication.shared.open(url) }
        }
        return nil
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let alert = UIAlertController(title: nil, message: message, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "حسناً", style: .default) { _ in completionHandler() })
        present(alert, animated: true)
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let alert = UIAlertController(title: nil, message: message, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "إلغاء", style: .cancel) { _ in completionHandler(false) })
        alert.addAction(UIAlertAction(title: "موافق", style: .default) { _ in completionHandler(true) })
        present(alert, animated: true)
    }

    func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String,
                 defaultText: String?, initiatedByFrame frame: WKFrameInfo,
                 completionHandler: @escaping (String?) -> Void) {
        let alert = UIAlertController(title: nil, message: prompt, preferredStyle: .alert)
        alert.addTextField { $0.text = defaultText }
        alert.addAction(UIAlertAction(title: "إلغاء", style: .cancel) { _ in completionHandler(nil) })
        alert.addAction(UIAlertAction(title: "موافق", style: .default) { _ in
            completionHandler(alert.textFields?.first?.text)
        })
        present(alert, animated: true)
    }

    /// Voice messages and the camera inside the page: iOS shows its own
    /// permission prompt, once, with the reason written in Info.plist.
    @available(iOS 15.0, *)
    func webView(_ webView: WKWebView, requestMediaCapturePermissionFor origin: WKSecurityOrigin,
                 initiatedByFrame frame: WKFrameInfo, type: WKMediaCaptureType,
                 decisionHandler: @escaping (WKPermissionDecision) -> Void) {
        decisionHandler(origin.host == host.split(separator: ":").first.map(String.init) ? .prompt : .deny)
    }

    // MARK: downloads

    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse,
                  suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try? FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let file = folder.appendingPathComponent(suggestedFilename)
        downloads[download] = file
        completionHandler(file)
    }

    func downloadDidFinish(_ download: WKDownload) {
        guard let file = downloads.removeValue(forKey: download) else { return }
        let share = UIActivityViewController(activityItems: [file], applicationActivities: nil)
        share.popoverPresentationController?.sourceView = view
        share.popoverPresentationController?.sourceRect = CGRect(x: view.bounds.midX, y: view.bounds.midY, width: 1, height: 1)
        present(share, animated: true)
    }

    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
        downloads.removeValue(forKey: download)
        let alert = UIAlertController(title: "تعذّر التنزيل", message: error.localizedDescription, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "حسناً", style: .default))
        present(alert, animated: true)
    }

    // MARK: offline

    private func showError() {
        guard errorView == nil else { return }
        let box = UIStackView()
        box.axis = .vertical
        box.spacing = 14
        box.alignment = .center
        box.translatesAutoresizingMaskIntoConstraints = false

        let icon = UIImageView(image: UIImage(systemName: "wifi.exclamationmark"))
        icon.tintColor = .brand
        icon.preferredSymbolConfiguration = .init(pointSize: 44)
        let title = UILabel()
        title.text = "لا يوجد اتصال"
        title.font = .systemFont(ofSize: 20, weight: .bold)
        let detail = UILabel()
        detail.text = "تأكد من الإنترنت ثم أعد المحاولة."
        detail.textColor = .secondaryLabel
        detail.numberOfLines = 0
        detail.textAlignment = .center

        let retry = UIButton(type: .system)
        var config = UIButton.Configuration.filled()
        config.title = "إعادة المحاولة"
        config.baseBackgroundColor = .brand
        config.cornerStyle = .large
        retry.configuration = config
        retry.addAction(UIAction { [weak self] _ in
            guard let self else { return }
            self.hideError()
            self.load(self.webView.url ?? URL(string: "https://\(self.host)/odoo")!)
        }, for: .touchUpInside)

        let other = UIButton(type: .system)
        other.setTitle("شركة أخرى", for: .normal)
        other.addAction(UIAction { _ in AppDelegate.shared.showCompanies() }, for: .touchUpInside)

        [icon, title, detail, retry, other].forEach(box.addArrangedSubview)
        let cover = UIView()
        cover.backgroundColor = .systemBackground
        cover.translatesAutoresizingMaskIntoConstraints = false
        cover.addSubview(box)
        view.addSubview(cover)
        NSLayoutConstraint.activate([
            cover.topAnchor.constraint(equalTo: webView.topAnchor),
            cover.bottomAnchor.constraint(equalTo: view.bottomAnchor),
            cover.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            cover.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            box.centerYAnchor.constraint(equalTo: cover.centerYAnchor),
            box.leadingAnchor.constraint(equalTo: cover.leadingAnchor, constant: 32),
            box.trailingAnchor.constraint(equalTo: cover.trailingAnchor, constant: -32),
        ])
        errorView = cover
    }

    private func hideError() {
        errorView?.removeFromSuperview()
        errorView = nil
    }
}

/// The page's message handler is held strongly by WebKit; going through this
/// keeps a replaced screen from living on behind the new one.
private final class WeakHandler: NSObject, WKScriptMessageHandler {
    weak var target: WKScriptMessageHandler?
    init(_ target: WKScriptMessageHandler) { self.target = target }
    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
        target?.userContentController(controller, didReceive: message)
    }
}
