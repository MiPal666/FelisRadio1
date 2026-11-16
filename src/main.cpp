#include <sailfishapp.h>
#include <QGuiApplication>
#include <QQuickView>
#include <QQmlContext>
#include <QScopedPointer>
#include <QUrl>
#include <QLocale>
#include <QTranslator>
#include "felisradio1_version.h"

int main(int argc, char *argv[])
{
    QScopedPointer<QGuiApplication> app(SailfishApp::application(argc, argv));
    app->setApplicationName(QStringLiteral("felisradio1"));
    app->setOrganizationName(QStringLiteral("cz.feliscatus"));
    const QUrl resources(QStringLiteral("file:///usr/share/harbour-felisradio1/"));
    QTranslator translation;
    translation.load(QLocale::system(), QStringLiteral("harbour-felisradio1"), QStringLiteral("-"),
                     resources.resolved(QUrl(QStringLiteral("translations"))).toLocalFile());
    app->installTranslator(&translation);
    QScopedPointer<QQuickView> view(SailfishApp::createView());
    view->rootContext()->setContextProperty(QStringLiteral("pythonImportPath"),
        resources.resolved(QUrl(QStringLiteral("python"))).toLocalFile());
    view->rootContext()->setContextProperty(QStringLiteral("pythonVendorPath"),
        resources.resolved(QUrl(QStringLiteral("vendor/python"))).toLocalFile());
    view->rootContext()->setContextProperty(QStringLiteral("appBuildVersion"), QStringLiteral(FELISRADIO1_BUILD_VERSION));
    view->rootContext()->setContextProperty(QStringLiteral("diagnosticsEnabled"),
        !qgetenv("FELISRADIO1_DIAGNOSTICS").isEmpty() && qgetenv("FELISRADIO1_DIAGNOSTICS") != "0");
    view->setSource(resources.resolved(QUrl(QStringLiteral("qml/harbour-felisradio1.qml"))));
    if (view->status() == QQuickView::Error) return 1;
    view->show();
    return app->exec();
}
