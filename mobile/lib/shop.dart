import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';
import 'main.dart';
import 'screens.dart';
import 'receipt.dart';

String pkr(num minor) => 'PKR ${(minor / 100).toStringAsFixed(2)}';

class StoreScreen extends StatefulWidget {
  const StoreScreen({super.key});
  @override
  State<StoreScreen> createState() => _StoreScreenState();
}

class _StoreScreenState extends State<StoreScreen> {
  late Future<dynamic> future;
  final Map<String, Map<String, dynamic>> cart = {};
  bool busy = false;
  @override
  void initState() {
    super.initState();
    refresh();
  }

  void refresh() {
    future = store.cached('catalogue', '/mobile/v1/catalogue');
  }

  void add(Map<String, dynamic> variant) {
    if (store.role != 'player') {
      toast(context, 'Sign in as a player to purchase merchandise.');
      return;
    }
    final id = variant['variant_id'].toString();
    final next = (cart[id]?['quantity'] as int? ?? 0) + 1;
    if (next > (variant['stock'] as num).toInt()) {
      toast(context, 'Only ${variant['stock']} left in this size.');
      return;
    }
    setState(() => cart[id] = {'variant': variant, 'quantity': next});
    toast(context, 'Size ${variant['size']} added to cart.');
  }

  int get subtotal => cart.values.fold(
      0,
      (sum, item) =>
          sum +
          ((item['variant']['price_minor'] as num).toInt() *
              (item['quantity'] as int)));

  Future<void> checkout() async {
    if (store.role != 'player') return;
    if (cart.isEmpty || busy) return;
    final confirmed = await showDialog<bool>(
        context: context,
        builder: (c) => AlertDialog(
              title: const Text('Confirm checkout'),
              content: Text(
                  '${cart.values.fold<int>(0, (sum, item) => sum + item['quantity'] as int)} items\n'
                  'Subtotal ${pkr(subtotal)}\nPayment: mock gateway\n\nStock and final total are confirmed by the server.'),
              actions: [
                TextButton(
                    onPressed: () => Navigator.pop(c, false),
                    child: const Text('Cancel')),
                FilledButton(
                    onPressed: () => Navigator.pop(c, true),
                    child: const Text('Pay now'))
              ],
            ));
    if (confirmed != true || !mounted) return;
    setState(() => busy = true);
    try {
      final receipt = await store.request('POST', '/mobile/v1/checkout', data: {
        'order_id': 'ord-${const Uuid().v4()}',
        'customer_id': store.email.isEmpty ? 'demo-customer' : store.email,
        'items': cart.values
            .map((item) => {
                  'variant_id': item['variant']['variant_id'],
                  'quantity': item['quantity'],
                })
            .toList(),
        'discount_code': null,
        'payment': {'token': 'tok_success'},
      });
      final receiptKey = 'receipts_${store.email}';
      final old = await store.local(receiptKey) as List? ?? [];
      await store.save(receiptKey, [receipt, ...old].take(20).toList());
      if (!mounted) return;
      setState(() {
        cart.clear();
        refresh();
      });
      Navigator.push(context,
          MaterialPageRoute(builder: (_) => ReceiptScreen(data: receipt)));
    } catch (e) {
      if (mounted) toast(context, e.toString());
    }
    if (mounted) setState(() => busy = false);
  }

  @override
  Widget build(BuildContext context) => RefreshIndicator(
        onRefresh: () async {
          setState(refresh);
          await future;
        },
        child: FutureBuilder<dynamic>(
            future: future,
            builder: (context, snapshot) {
              final products =
                  snapshot.data is List ? snapshot.data as List : [];
              return ListView(padding: const EdgeInsets.all(15), children: [
                header('Club store', 'Official merchandise for matchday'),
                if (snapshot.connectionState == ConnectionState.waiting)
                  const LinearProgressIndicator(),
                if (snapshot.hasError) Text(snapshot.error.toString()),
                if (products.isEmpty)
                  const Card(
                      child: ListTile(
                          title: Text('No products available'),
                          subtitle: Text(
                              'Connect to the team server or pull to refresh.'))),
                ...products.map((product) => Card(
                    child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              Container(
                                  height: 116,
                                  decoration: BoxDecoration(
                                      color: const Color(0xff194453),
                                      borderRadius: BorderRadius.circular(14)),
                                  child: const Icon(Icons.checkroom,
                                      size: 68, color: Color(0xff54e0cf))),
                              const SizedBox(height: 14),
                              Text(product['name'].toString(),
                                  style: const TextStyle(
                                      fontSize: 20,
                                      fontWeight: FontWeight.bold)),
                              const SizedBox(height: 3),
                              Text(product['category'].toString().toUpperCase(),
                                  style: const TextStyle(
                                      fontSize: 11,
                                      letterSpacing: 1.5,
                                      color: Color(0xff54e0cf))),
                              const SizedBox(height: 12),
                              ...((product['variants'] as List?) ?? [])
                                  .map((raw) {
                                final variant = Map<String, dynamic>.from(raw);
                                return Padding(
                                    padding:
                                        const EdgeInsets.symmetric(vertical: 5),
                                    child: Row(children: [
                                      Expanded(
                                          child: Column(
                                              crossAxisAlignment:
                                                  CrossAxisAlignment.start,
                                              children: [
                                            Text('Size ${variant['size']}',
                                                style: const TextStyle(
                                                    fontWeight:
                                                        FontWeight.bold)),
                                            Text(
                                                '${variant['stock']} available • ${pkr(variant['price_minor'] as num)}',
                                                style: const TextStyle(
                                                    fontSize: 12,
                                                    color: Colors.white70)),
                                          ])),
                                      const SizedBox(width: 8),
                                      FilledButton(
                                          onPressed:
                                              store.role == 'player' && (variant['stock'] as num) > 0
                                                  ? () => add(variant)
                                                  : null,
                                          child: const Text('Add')),
                                    ]));
                              }),
                            ])))),
                header('Your cart', 'Review items before mock payment'),
                if (cart.isEmpty)
                  const Card(
                      child: ListTile(
                          leading: Icon(Icons.shopping_bag_outlined),
                          title: Text('Your cart is empty'))),
                ...cart.entries.map((entry) {
                  final variant =
                      entry.value['variant'] as Map<String, dynamic>;
                  final quantity = entry.value['quantity'] as int;
                  return Card(
                      child: ListTile(
                    title: Text('Jersey • size ${variant['size']}'),
                    subtitle: Text(
                        '$quantity × ${pkr(variant['price_minor'] as num)}'),
                    trailing: IconButton(
                        tooltip: 'Remove one item',
                        icon: const Icon(Icons.remove_circle_outline),
                        onPressed: () => setState(() {
                              if (quantity == 1) {
                                cart.remove(entry.key);
                              } else {
                                entry.value['quantity'] = quantity - 1;
                              }
                            })),
                  ));
                }),
                if (cart.isNotEmpty) ...[
                  Padding(
                      padding: const EdgeInsets.all(12),
                      child: Text('Subtotal  ${pkr(subtotal)}',
                          textAlign: TextAlign.end,
                          style: const TextStyle(
                              fontSize: 18, fontWeight: FontWeight.bold))),
                  ElevatedButton.icon(
                      onPressed: busy ? null : checkout,
                      icon: const Icon(Icons.lock_outline),
                      label: Text(busy ? 'Processing…' : 'Checkout securely')),
                ],
                header('Past receipts',
                    'Saved on this device for offline viewing'),
                FutureBuilder<dynamic>(
                    future: store.local('receipts_${store.email}'),
                    builder: (context, saved) {
                      final receipts =
                          saved.data is List ? saved.data as List : [];
                      if (receipts.isEmpty)
                        return const Card(
                            child: ListTile(title: Text('No purchases yet')));
                      return Column(
                          children: receipts
                              .map((item) => Card(
                                      child: ListTile(
                                    leading: const Icon(Icons.receipt_long,
                                        color: Color(0xff54e0cf)),
                                    title: Text(item['order_id'].toString(),
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis),
                                    subtitle:
                                        Text(pkr(item['total_minor'] as num)),
                                    trailing: const Icon(Icons.chevron_right),
                                    onTap: () => Navigator.push(
                                        context,
                                        MaterialPageRoute(
                                            builder: (_) =>
                                                ReceiptScreen(data: item))),
                                  )))
                              .toList());
                    }),
              ]);
            }),
      );
}
