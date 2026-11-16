import QtQuick 2.6
Item {
 property var handlers: ({})
 signal error(string traceback)
 function addImportPath(path) {}
 function setHandler(name, handler) { handlers[name]=handler }
 function importModule(name, callback) { callback() }
 function call(name, args, callback) {
   console.log("CALL",name,JSON.stringify(args))
   if (name.indexOf("initialize") >= 0) callback({url:"https://example.invalid/radio"})
   else if (name.endsWith(".select")) handlers.cast_candidate({request:args[2]})
   else if (name.endsWith(".local")) handlers.local_selected({request:args[0]})
   else if (name.endsWith(".commit")) handlers.output_selected({request:args[0],active:args[1],playRequest:args[2],deviceId:"speaker",name:"Test",state:"PLAYING"})
 }
}
