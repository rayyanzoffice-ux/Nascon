import 'package:flutter/material.dart';

class ReceiptScreen extends StatelessWidget{
  final dynamic data;
  const ReceiptScreen({super.key,required this.data});
  @override Widget build(BuildContext context){
    final payload=data['receipt']['payload'];
    return Scaffold(appBar:AppBar(title:const Text('Payment receipt')),
      body:ListView(padding:const EdgeInsets.all(20),children:[
        const Icon(Icons.check_circle,color:Color(0xff3dddc9),size:75),
        const SizedBox(height:12),
        const Text('Payment successful',textAlign:TextAlign.center,
          style:TextStyle(fontSize:24,fontWeight:FontWeight.bold)),
        const SizedBox(height:25),
        Card(child:Padding(padding:const EdgeInsets.all(18),child:Column(
          crossAxisAlignment:CrossAxisAlignment.start,children:[
            Text('Receipt • ${data['order_id']}',style:const TextStyle(fontSize:18,fontWeight:FontWeight.bold)),
            const Divider(),
            Text('Items: ${(data['items'] as List).length}'),
            Text('Subtotal: PKR ${((data['subtotal_minor'] as num)/100).toStringAsFixed(2)}'),
            Text('Discount: PKR ${((data['discount_minor'] as num)/100).toStringAsFixed(2)}'),
            const SizedBox(height:10),
            Text('TOTAL  PKR ${((data['total_minor'] as num)/100).toStringAsFixed(2)}',
              style:const TextStyle(fontSize:19,fontWeight:FontWeight.bold,color:Color(0xff3dddc9))),
            const SizedBox(height:12),
            Text('Paid at: ${payload['paid_at']}'),
            const SizedBox(height:8),
            const Text('Server-generated and cryptographically signed PDF receipt.'),
          ]))),
        const SizedBox(height:20),
        ElevatedButton(onPressed:()=>Navigator.pop(context),child:const Text('Done')),
      ]),
    );
  }
}
