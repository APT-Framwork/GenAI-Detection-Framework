
const socket = new WebSocket("ws://localhost:8006/websocket");

window.pwd = "";
socket.onopen = (event) =>{
	const valeurCachee = document.getElementById('session_uuid').value;
	socket.send(valeurCachee)
	
}



var term = new window.Terminal({
    cursorBlink: true,
    cols: 200,
    fontFamily: 'Courier New'
});
term.open(document.getElementById('terminal'));
term.write('Hello Red Team <^-^>');
function init() {
    if (term._initialized) {
        return;
    }

    term._initialized = true;

    term.prompt = () => {
        term.write('\r\n$ ');
    };
    prompt(term);

    term.onData(e => {
        switch (e) {
            case '\u0003': // Ctrl+C
                term.write('^C');
                prompt(term);
                break;
            case '\r': // Enter
                runCommand(term, command);
                command = '';
                break;
            case '\u007F': // Backspace (DEL)
                // Do not delete the prompt
                if (term._core.buffer.x > 2) {
                    term.write('\b \b');
                    if (command.length > 0) {
                        command = command.substr(0, command.length - 1);
                    }
                }
                break;
            case '\u0009':
                console.log('tabbed', output, ["dd", "ls"]);
                break;
            default:
                if (e >= String.fromCharCode(0x20) && e <= String.fromCharCode(0x7E) || e >= '\u00a0') {
                    command += e;
                    term.write(e);
                }
        }
    });
}

function clearInput(command) {
    var inputLengh = command.length;
    for (var i = 0; i < inputLengh; i++) {
        term.write('\b \b');
    }
}
function prompt(term) {
    command = '';
    term.write("\r\n$ ");
}
socket.onmessage = (event) => {
     
    donnes = event.data;
    term.write(donnes);
   
}

function runCommand(term, command) {
    if (command.length > 0) {
        //clearInput(command);
        socket.send(command + '\n');
        return;
    }
}

function f1(commande){
    command=command+commande;
    term.write(commande);
}
init();
