import UIKit

/// The first screen: which company. Shown once; afterwards the app opens
/// straight into the last company, and "switch company" brings it back.
final class CompanyViewController: UIViewController, UITextFieldDelegate {
    private let field = UITextField()
    private let button = UIButton(type: .system)
    private let errorLabel = UILabel()
    private let savedStack = UIStackView()
    private let savedTitle = UILabel()
    // A context menu holds its delegate weakly; these keep them alive.
    private var menus: [ForgetMenu] = []

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = UIColor(red: 0.957, green: 0.965, blue: 0.980, alpha: 1)
        view.semanticContentAttribute = .forceRightToLeft
        navigationController?.setNavigationBarHidden(true, animated: false)

        let scroll = UIScrollView()
        scroll.keyboardDismissMode = .interactive
        scroll.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(scroll)

        let stack = UIStackView()
        stack.axis = .vertical
        stack.spacing = 10
        stack.semanticContentAttribute = .forceRightToLeft
        stack.translatesAutoresizingMaskIntoConstraints = false
        scroll.addSubview(stack)

        NSLayoutConstraint.activate([
            scroll.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),
            scroll.bottomAnchor.constraint(equalTo: view.keyboardLayoutGuide.topAnchor),
            scroll.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            scroll.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            stack.topAnchor.constraint(equalTo: scroll.contentLayoutGuide.topAnchor, constant: 40),
            stack.bottomAnchor.constraint(equalTo: scroll.contentLayoutGuide.bottomAnchor, constant: -28),
            stack.leadingAnchor.constraint(equalTo: scroll.frameLayoutGuide.leadingAnchor, constant: 28),
            stack.trailingAnchor.constraint(equalTo: scroll.frameLayoutGuide.trailingAnchor, constant: -28),
        ])

        let logo = UIImageView(image: UIImage(named: "Logo"))
        logo.contentMode = .scaleAspectFit
        logo.layer.cornerRadius = 22
        logo.clipsToBounds = true
        logo.heightAnchor.constraint(equalToConstant: 96).isActive = true
        stack.addArrangedSubview(logo)

        stack.addArrangedSubview(label("مقياس", size: 30, weight: .bold, color: .brand, center: true))
        stack.addArrangedSubview(label("محاسبة المقاولات والمشاريع", size: 15, color: .secondaryLabel, center: true))
        stack.setCustomSpacing(36, after: stack.arrangedSubviews.last!)

        stack.addArrangedSubview(label("رمز الشركة", size: 16, weight: .semibold, color: .label))

        field.placeholder = "alamana"
        field.font = .systemFont(ofSize: 17)
        field.keyboardType = .URL
        field.autocapitalizationType = .none
        field.autocorrectionType = .no
        field.returnKeyType = .go
        field.textAlignment = .left
        field.semanticContentAttribute = .forceLeftToRight
        field.backgroundColor = .white
        field.layer.cornerRadius = 12
        field.layer.borderWidth = 1
        field.layer.borderColor = UIColor(red: 0.835, green: 0.863, blue: 0.902, alpha: 1).cgColor
        field.leftView = UIView(frame: CGRect(x: 0, y: 0, width: 14, height: 1))
        field.leftViewMode = .always
        field.delegate = self
        field.heightAnchor.constraint(equalToConstant: 54).isActive = true
        stack.addArrangedSubview(field)

        stack.addArrangedSubview(label(
            "اكتب رمز شركتك كما أعطاك إياه المسؤول، أو عنوان السيرفر كاملاً. الرمز وحده يعني \u{200E}\(Companies.domain)",
            size: 13, color: .secondaryLabel))

        errorLabel.font = .systemFont(ofSize: 14)
        errorLabel.textColor = .systemRed
        errorLabel.numberOfLines = 0
        errorLabel.textAlignment = .right
        stack.addArrangedSubview(errorLabel)

        button.setTitle("متابعة", for: .normal)
        button.titleLabel?.font = .systemFont(ofSize: 17, weight: .bold)
        button.setTitleColor(.white, for: .normal)
        button.backgroundColor = .brand
        button.layer.cornerRadius = 12
        button.heightAnchor.constraint(equalToConstant: 54).isActive = true
        button.addTarget(self, action: #selector(go), for: .touchUpInside)
        stack.addArrangedSubview(button)
        stack.setCustomSpacing(36, after: button)

        savedTitle.text = "شركاتك"
        savedTitle.font = .systemFont(ofSize: 16, weight: .semibold)
        savedTitle.textAlignment = .right
        stack.addArrangedSubview(savedTitle)
        savedStack.axis = .vertical
        savedStack.spacing = 8
        stack.addArrangedSubview(savedStack)
        showSaved()
    }

    override var preferredStatusBarStyle: UIStatusBarStyle { .darkContent }

    private func label(_ text: String, size: CGFloat, weight: UIFont.Weight = .regular,
                       color: UIColor, center: Bool = false) -> UILabel {
        let label = UILabel()
        label.text = text
        label.font = .systemFont(ofSize: size, weight: weight)
        label.textColor = color
        label.numberOfLines = 0
        label.textAlignment = center ? .center : .right
        return label
    }

    private func showSaved() {
        savedStack.arrangedSubviews.forEach { $0.removeFromSuperview() }
        menus.removeAll()
        for host in Companies.all {
            let item = UIButton(type: .system)
            item.setTitle(host, for: .normal)
            item.titleLabel?.font = .systemFont(ofSize: 16)
            item.setTitleColor(.brand, for: .normal)
            item.contentHorizontalAlignment = .left
            item.backgroundColor = .white
            item.layer.cornerRadius = 12
            item.layer.borderWidth = 1
            item.layer.borderColor = UIColor(red: 0.835, green: 0.863, blue: 0.902, alpha: 1).cgColor
            var config = UIButton.Configuration.plain()
            config.contentInsets = NSDirectionalEdgeInsets(top: 0, leading: 14, bottom: 0, trailing: 14)
            item.configuration = config
            item.setTitle(host, for: .normal)
            item.heightAnchor.constraint(equalToConstant: 54).isActive = true
            item.addAction(UIAction { _ in AppDelegate.shared.open(host: host) }, for: .touchUpInside)
            let menu = ForgetMenu(host: host) { [weak self] in self?.showSaved() }
            menus.append(menu)
            item.addInteraction(UIContextMenuInteraction(delegate: menu))
            savedStack.addArrangedSubview(item)
        }
        savedTitle.isHidden = Companies.all.isEmpty
    }

    func textFieldShouldReturn(_ textField: UITextField) -> Bool {
        go()
        return true
    }

    @objc private func go() {
        guard let host = Companies.host(for: field.text ?? "") else {
            errorLabel.text = "اكتب الرمز بحروف إنجليزية وأرقام فقط، مثل alamana"
            return
        }
        errorLabel.text = nil
        button.isEnabled = false
        button.setTitle("جارٍ التحقق…", for: .normal)
        Companies.check(host) { [weak self] ok in
            guard let self else { return }
            self.button.isEnabled = true
            self.button.setTitle("متابعة", for: .normal)
            if ok {
                AppDelegate.shared.open(host: host)
            } else {
                self.errorLabel.text = "لم نصل إلى \u{200E}\(host)\u{200F}. تأكد من الرمز ومن اتصال الإنترنت."
            }
        }
    }
}

/// Long press on a saved company: remove it from this phone.
private final class ForgetMenu: NSObject, UIContextMenuInteractionDelegate {
    let host: String
    let done: () -> Void
    init(host: String, done: @escaping () -> Void) { self.host = host; self.done = done }

    func contextMenuInteraction(_ interaction: UIContextMenuInteraction,
                                configurationForMenuAtLocation location: CGPoint) -> UIContextMenuConfiguration? {
        UIContextMenuConfiguration(identifier: nil, previewProvider: nil) { _ in
            UIMenu(children: [UIAction(title: "إزالة من هذا الجوال", image: UIImage(systemName: "trash"),
                                       attributes: .destructive) { [self] _ in
                Companies.forget(host)
                done()
            }])
        }
    }
}
