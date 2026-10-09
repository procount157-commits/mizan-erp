import UIKit
import UserNotifications

extension Notification.Name {
    static let miqyasPushToken = Notification.Name("miqyasPushToken")
}

extension UIColor {
    static let brand = UIColor(named: "Brand") ?? UIColor(red: 0.10, green: 0.24, blue: 0.43, alpha: 1)
}

@main
final class AppDelegate: UIResponder, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    var window: UIWindow?
    private(set) static var pushToken: String?

    static var shared: AppDelegate { UIApplication.shared.delegate as! AppDelegate }

    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions options: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        let window = UIWindow(frame: UIScreen.main.bounds)
        window.tintColor = .brand
        self.window = window

        if let item = options?[.shortcutItem] as? UIApplicationShortcutItem, item.type == "switch" {
            showCompanies()
            window.makeKeyAndVisible()
            return false
        }
        if let host = Companies.current {
            open(host: host)
        } else {
            showCompanies()
        }
        window.makeKeyAndVisible()
        // Already allowed on an earlier launch: refresh the token silently.
        UNUserNotificationCenter.current().getNotificationSettings { settings in
            if settings.authorizationStatus == .authorized {
                DispatchQueue.main.async { application.registerForRemoteNotifications() }
            }
        }
        return true
    }

    // MARK: screens

    func showCompanies() {
        window?.rootViewController = UINavigationController(rootViewController: CompanyViewController())
    }

    func open(host: String, url: URL? = nil) {
        Companies.use(host)
        window?.rootViewController = WebViewController(host: host, start: url)
    }

    /// "Switch company" from a long press on the app icon.
    func application(_ application: UIApplication, performActionFor item: UIApplicationShortcutItem,
                     completionHandler: @escaping (Bool) -> Void) {
        showCompanies()
        completionHandler(true)
    }

    // MARK: notifications

    /// Asked once the person has signed in, when the reason is obvious —
    /// not on the first screen, before they know what the app is.
    func askForNotifications() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { granted, _ in
            guard granted else { return }
            DispatchQueue.main.async { UIApplication.shared.registerForRemoteNotifications() }
        }
    }

    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken token: Data) {
        let hex = token.map { String(format: "%02x", $0) }.joined()
        AppDelegate.pushToken = hex
        NotificationCenter.default.post(name: .miqyasPushToken, object: hex)
    }

    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
        NSLog("Miqyas: notifications unavailable: \(error.localizedDescription)")
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                withCompletionHandler completion: @escaping (UNNotificationPresentationOptions) -> Void) {
        completion([.banner, .list, .sound])
    }

    /// A tap opens the record the message is about, in the company it came
    /// from — a phone can follow more than one.
    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
                                withCompletionHandler completion: @escaping () -> Void) {
        defer { completion() }
        if #available(iOS 16.0, *) { center.setBadgeCount(0) }
        guard let link = response.notification.request.content.userInfo["url"] as? String,
              let url = URL(string: link), let host = url.host else { return }
        let fullHost = url.port.map { "\(host):\($0)" } ?? host
        if let web = window?.rootViewController as? WebViewController, web.host == fullHost {
            web.load(url)
        } else {
            open(host: fullHost, url: url)
        }
    }
}
