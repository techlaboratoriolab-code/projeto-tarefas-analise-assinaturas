from flask import jsonify

def handler(request):
    return jsonify({
        'status': 'ok',
        'service': 'LAB TISS Processor',
        'version': '1.0.0'
    })
