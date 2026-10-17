import 'package:flutter/material.dart';
import 'screens.dart';
import 'shop.dart';

class ReceiptScreen extends StatelessWidget {
  final dynamic data;
  const ReceiptScreen({super.key, required this.data});
  @override
  Widget build(BuildContext context) {
    final receipt = data['receipt'] as Map? ?? {};
    final payload = receipt['payload'] as Map? ?? {};
    final items = data['items'] as List? ?? [];
    return Scaffold(
      appBar: AppBar(title: const Text('Payment receipt')),
      body: Column(children: [
        const SyncBanner(),
        Expanded(
            child: ListView(padding: const EdgeInsets.all(20), children: [
          const Icon(Icons.check_circle, color: Color(0xff54e0cf), size: 70),
          const SizedBox(height: 12),
          const Text('Payment successful',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold)),
          const SizedBox(height: 5),
          const Text('Your official NaSCon merchandise is confirmed.',
              textAlign: TextAlign.center,
              style: TextStyle(color: Colors.white70)),
          const SizedBox(height: 22),
          Card(
              child: Padding(
                  padding: const EdgeInsets.all(18),
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('ORDER  ${data['order_id']}',
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                                fontSize: 16,
                                fontWeight: FontWeight.bold,
                                color: Color(0xff54e0cf))),
                        const Divider(height: 28),
                        ...items.map((item) => Padding(
                            padding: const EdgeInsets.only(bottom: 10),
                            child: Row(children: [
                              Expanded(
                                  child: Text(
                                      '${item['variant_id']}  × ${item['quantity']}')),
                              Text(pkr((item['unit_price_minor'] as num) *
                                  (item['quantity'] as num))),
                            ]))),
                        const Divider(),
                        Row(children: [
                          const Expanded(child: Text('Subtotal')),
                          Text(pkr(data['subtotal_minor'] as num))
                        ]),
                        const SizedBox(height: 7),
                        Row(children: [
                          const Expanded(child: Text('Discount')),
                          Text(pkr(data['discount_minor'] as num))
                        ]),
                        const Divider(height: 25),
                        Row(children: [
                          const Expanded(
                              child: Text('TOTAL',
                                  style:
                                      TextStyle(fontWeight: FontWeight.bold))),
                          Text(pkr(data['total_minor'] as num),
                              style: const TextStyle(
                                  fontSize: 20,
                                  fontWeight: FontWeight.w900,
                                  color: Color(0xff54e0cf)))
                        ]),
                        const SizedBox(height: 20),
                        Text('Paid at  ${payload['paid_at'] ?? '—'}',
                            style: const TextStyle(color: Colors.white70)),
                        const SizedBox(height: 5),
                        Text(
                            'Payment  ${data['payment']?['state'] ?? 'captured'}',
                            style: const TextStyle(color: Colors.white70)),
                        const SizedBox(height: 10),
                        const Text(
                            'Server signed receipt • saved on this device',
                            style:
                                TextStyle(fontSize: 12, color: Colors.white70)),
                        Text('Signature  ${receipt['signature'] ?? '—'}',
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                                fontSize: 10, color: Colors.white54)),
                      ]))),
          const SizedBox(height: 20),
          ElevatedButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Done')),
        ])),
      ]),
    );
  }
}
